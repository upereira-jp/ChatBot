from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session
import json
import os
import traceback
from datetime import datetime, time, date, timedelta

# --- SUAS IMPORTAÇÕES DE MÓDULOS LOCAIS ---
# from whatsapp_api import send_whatsapp_message
# from nlp_processor import process_message_with_ai
import database # Importa o módulo inteiro para evitar circular import
import google_calendar_service # Importa o módulo inteiro para evitar circular import

# Desempacotando as funções do database para manter a compatibilidade com o código original
get_db = database.get_db
get_token = database.get_token
save_token = database.save_token
create_compromisso = database.create_compromisso
get_compromissos_do_dia = database.get_compromissos_do_dia
update_compromisso = database.update_compromisso
delete_compromisso = database.delete_compromisso
get_compromisso_por_id = database.get_compromisso_por_id

# Desempacotando as funções de autenticação do google_calendar_service para manter a compatibilidade com o código original
google_auth_flow_start = google_calendar_service.google_auth_flow_start
google_auth_flow_callback = google_calendar_service.google_auth_flow_callback


# --- MOCK DA IA PARA TESTE (Contorna o erro 429 da OpenAI) ---
class MockAgendaAction:
    """Simula a saída da IA para testar o fluxo completo."""
    def __init__(self):
        # Hardcoded data para uma ação de 'agendar' bem-sucedida
        self.action = "agendar"
        self.titulo = "Reunião de Teste (Mock IA)"
        # Define a data/hora para daqui a 1 hora
        self.data_hora = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        self.assunto = "Teste de Sincronização"
        self.duracao = 60 # minutos
        self.recorrencia = None
        self.id_compromisso = None

def process_message_with_ai(message_text):
    """Função mock que substitui a chamada real à OpenAI."""
    print("LOG (Mock IA): Retornando ação de agendamento de teste para contornar erro 429.", flush=True)
    return MockAgendaAction()

# --- FIM DO MOCK ---

# Inicializa a aplicação FastAPI
app = FastAPI()

# ID Fixo para o token na base de dados
MAIN_USER_ID = "main_user"

# 🔒 TOKEN DE VERIFICAÇÃO DO META
# Usando os.getenv para o token de verificação, mas mantendo o fallback para o teste
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "meu_token_real_123")


# --- FUNÇÃO DE PROCESSAMENTO EM SEGUNDO PLANO ---
def process_message_background(data: dict, db: Session):
    """
    Função que processa a lógica de negócios real (IA, DB, Google Calendar, Resposta do WhatsApp).
    Executada em background para garantir resposta imediata ao Meta.
    """
    try:
        print(f"LOG PAYLOAD (Background): {json.dumps(data)}", flush=True)

        # Verifica se é um evento de mensagem (formato Meta)
        if not (data.get('entry') and
                data['entry'][0].get('changes') and
                data['entry'][0]['changes'][0].get('value') and
                data['entry'][0]['changes'][0]['value'].get('messages')):

            print("LOG (Background): Payload recebido não é uma mensagem de usuário para processamento.", flush=True)
            return

        # Extração de dados da mensagem
        message_data = data['entry'][0]['changes'][0]['value']['messages'][0]
        message_text = message_data['text']['body']
        from_number = message_data['from']

        # Processamento de IA (AGORA USANDO O MOCK)
        ai_result = process_message_with_ai(message_text)

        # Lógica de Ação
        response_message = ""

        # Verifique se o token do Google Calendar está disponível
        token_record = get_token(db, user_id=MAIN_USER_ID)
        
        # Passar a string JSON bruta para o google_calendar_service
        google_token_json = token_record.token_json if token_record else None

        # Ações para criar, reagendar, cancelar e consultar compromissos
        if ai_result.action == "agendar":
            if not ai_result.data_hora:
                response_message = "Não consegui identificar a data e hora. Por favor, especifique melhor."
            else:
                compromisso = create_compromisso(
                    db,
                    titulo=ai_result.titulo,
                    data_hora=ai_result.data_hora,
                    assunto=ai_result.assunto,
                    duracao=ai_result.duracao,
                    recorrencia=ai_result.recorrencia
                )
                response_message = f"Compromisso agendado com sucesso! ID Local: {compromisso.id}. Título: {compromisso.titulo} em {compromisso.data_hora.strftime('%d/%m/%Y %H:%M')}."

                if google_token_json:
                    # Chamada corrigida com o prefixo do módulo
                    event_id = google_calendar_service.create_google_event(google_token_json, compromisso)
                    if event_id:
                        update_compromisso(db, compromisso.id, {"google_event_id": event_id})
                        response_message += f" Sincronizado com o Google Calendar."
                else:
                    response_message += f" \n\n⚠️ **Atenção:** O Google Calendar não está sincronizado. Acesse a rota /auth/google/start para autorizar."

        elif ai_result.action == "reagendar":
            if not ai_result.id_compromisso or not ai_result.data_hora:
                response_message = "Para reagendar, preciso do ID do compromisso e da nova data/hora."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    update_compromisso(db, compromisso.id, {"data_hora": ai_result.data_hora})
                    response_message = f"Compromisso ID {compromisso.id} reagendado para {ai_result.data_hora.strftime('%d/%m/%Y %H:%M')}."

                    if google_token_json and compromisso.google_event_id:
                        # Chamada corrigida com o prefixo do módulo
                        google_calendar_service.update_google_event(google_token_json, compromisso)
                        response_message += " Sincronizado com o Google Calendar."
                else:
                    response_message = f"Compromisso com ID {ai_result.id_compromisso} não encontrado."

        elif ai_result.action == "cancelar":
            if not ai_result.id_compromisso:
                response_message = "Para cancelar, preciso do ID do compromisso."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    delete_compromisso(db, compromisso.id)
                    response_message = f"Compromisso ID {compromisso.id} cancelado com sucesso."

                    if google_token_json and compromisso.google_event_id:
                        # Chamada corrigida com o prefixo do módulo
                        google_calendar_service.delete_google_event(google_token_json, compromisso.google_event_id)
                        response_message += " Sincronizado com o Google Calendar."
                else:
                    response_message = f"Compromisso com ID {ai_result.id_compromisso} não encontrado."

        elif ai_result.action == "consultar":
            data_consulta = ai_result.data_hora.date() if ai_result.data_hora else datetime.now().date()
            compromissos = get_compromissos_do_dia(db, datetime.combine(data_consulta, datetime.min.time()))

            if compromissos:
                lista = "\n".join([f"ID {c.id}: {c.titulo} ({c.assunto}) às {c.data_hora.strftime('%H:%M')}" for c in compromissos])
                response_message = f"Compromissos para {data_consulta.strftime('%d/%m/%Y')}:\n{lista}"
            else:
                response_message = f"Nenhum compromisso encontrado para {data_consulta.strftime('%d/%m/%Y')}."

        else:
            response_message = "Desculpe, não entendi a sua solicitação. Tente algo como: 'Agendar reunião amanhã às 10h' ou 'Consultar agenda de hoje'."

        # Envia a resposta de volta via WhatsApp
        # NOTE: A função send_whatsapp_message precisa ser importada ou mockada
        # Para este teste, assumimos que ela está disponível.
        # send_whatsapp_message(from_number, response_message)
        print(f"LOG (WhatsApp Send): Tentando enviar mensagem para {from_number}: {response_message}", flush=True)


    except Exception as e:
        # Tenta enviar a mensagem de erro, se o from_number estiver disponível
        try:
            # Tenta extrair o número de telefone em caso de erro
            from_number = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
            # send_whatsapp_message(from_number, "Ocorreu um erro interno ao processar sua solicitação.")
            print(f"LOG (WhatsApp Send Error): Tentando enviar erro para {from_number}", flush=True)
        except:
            pass # Se não conseguir extrair o número, ignora.

        error_detail = f"Erro no processamento da mensagem (Background): {e}\n{traceback.format_exc()}"
        print(error_detail, flush=True)


# --- ROTAS DE AUTENTICAÇÃO DO GOOGLE CALENDAR ---

@app.get("/auth/google/start")
async def google_auth_start():
    try:
        auth_url = google_auth_flow_start()
        return RedirectResponse(auth_url)
    except Exception as e:
        print(f"Erro ao iniciar o fluxo de autenticação: {e}", flush=True)
        return HTMLResponse(
            content=f"<h1>Erro ao iniciar o Google Auth</h1><p>Detalhe: {e}</p>",
            status_code=500
        )

@app.get("/auth/google/callback")
async def google_auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        full_url = str(request.url)
        token_info = google_auth_flow_callback(full_url)

        # O token_info já é a string JSON, não precisa de json.dumps()
        save_token(db, user_id=MAIN_USER_ID, token_json=token_info)

        return HTMLResponse(
            content="<h1>✅ Autenticação Concluída com Sucesso!</h1><p>O Google Calendar está agora sincronizado com o seu bot do WhatsApp. Você pode fechar esta página.</p>",
            status_code=200
        )

    except Exception as e:
        print(f"Erro no callback do Google: {e}", flush=True)
        return HTMLResponse(
            content=f"<h1>❌ Erro na Autenticação</h1><p>Ocorreu um problema ao salvar o token. Detalhe: {e}</p>",
            status_code=500
        )

# --- ROTA TEMPORÁRIA DE LIMPEZA DE TOKEN ---
@app.get("/admin/clear-token")
def clear_token(db: Session = Depends(get_db)):
    """Rota temporária para deletar o token do Google Calendar do DB."""
    try:
        # Tenta obter o registro do token
        token_record = get_token(db, user_id=MAIN_USER_ID)
        
        if token_record:
            # Deleta o registro e commita
            db.delete(token_record)
            db.commit()
            return {"status": "ok", "message": "Token do Google Calendar deletado com sucesso. Por favor, refaça a autenticação."}
        
        return {"status": "ok", "message": "Nenhum token encontrado para deletar."}
    except Exception as e:
        # Se houver um erro, tenta dar rollback e retorna o erro
        db.rollback()
        print(f"Erro ao deletar token: {e}", flush=True)
        return {"status": "error", "message": f"Erro ao deletar token: {e}"}


# --- ROTAS DA APLICAÇÃO ---

@app.get("/")
def read_root():
    return {"message": "Servidor está funcionando!"}

# --- ROTA DE VERIFICAÇÃO DO WEBHOOK (GET) ---
# Esta é a rota crítica que estava falhando
@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    """
    Lida com a requisição GET de verificação de URL do Meta.
    """
    # Pega os parâmetros da URL
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # Verifica se os parâmetros existem
    if mode and token:
        # Verifica se o modo é 'subscribe' e se o token bate
        if mode == "subscribe" and token == VERIFY_TOKEN:
            # O Meta espera PlainTextResponse (texto puro), não HTML.
            # Convertemos challenge para string para garantir.
            print(f"--- SUCESSO: Webhook verificado. Retornando challenge: {challenge} ---", flush=True)
            return PlainTextResponse(content=str(challenge), status_code=200)
        else:
            print(f"--- FALHA: Token recebido ({token}) diferente do esperado ou modo errado ---", flush=True)
            raise HTTPException(status_code=403, detail="Token de verificação incorreto")

    # Caso acesse pelo navegador sem parâmetros
    print("--- AVISO: Acesso GET sem parâmetros (Normal se for acesso via navegador) ---", flush=True)
    raise HTTPException(status_code=400, detail="Parâmetros ausentes. Esta rota é para uso do Meta/WhatsApp.")


# --- ROTA DE RECEBIMENTO DE MENSAGENS (POST) ---
@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Recebe o payload do Meta e responde imediatamente.
    """
    print("--- POST RECEBIDO: Iniciando processamento ---", flush=True)

    try:
        data = await request.json()

        # Agenda a função pesada para background
        background_tasks.add_task(process_message_background, data, db)

        return {"status": "ok", "message": "Evento agendado."}

    except Exception as e:
        error_detail = f"Erro FATAL no POST: {e}\n{traceback.format_exc()}"
        print(error_detail, flush=True)
        raise HTTPException(status_code=500, detail="Erro ao processar payload.")
