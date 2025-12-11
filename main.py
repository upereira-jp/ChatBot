from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
import json
from datetime import datetime
from whatsapp_api import send_whatsapp_message
from nlp_processor import process_message_with_ai, AgendaAction
from database import (
    get_db,
    get_token,
    save_token,
    create_compromisso,
    get_compromissos_do_dia,
    update_compromisso,
    delete_compromisso,
    get_compromisso_por_id
)
from google_calendar_service import (
    create_google_event,
    update_google_event,
    delete_google_event,
    # --- NOVAS FUNÇÕES NECESSÁRIAS ---
    google_auth_flow_start,
    google_auth_flow_callback 
)

# Inicializa a aplicação FastAPI
app = FastAPI()

# ID Fixo para o token na base de dados, já que é um bot de uso único.
MAIN_USER_ID = "main_user" 

# --- ROTAS DE AUTENTICAÇÃO DO GOOGLE CALENDAR ---

## 🔑 Rota 1: Iniciar o Fluxo OAuth
@app.get("/auth/google/start")
async def google_auth_start():
    """
    Inicia o fluxo de autorização do Google.
    Gera a URL de consentimento e redireciona o usuário para o Google.
    """
    try:
        auth_url = google_auth_flow_start()
        # Redireciona o navegador do usuário para a página de login do Google
        return RedirectResponse(auth_url)
    except Exception as e:
        print(f"Erro ao iniciar o fluxo de autenticação: {e}")
        return HTMLResponse(
            content=f"<h1>Erro ao iniciar o Google Auth</h1><p>Detalhe: {e}</p>",
            status_code=500
        )

## 🔄 Rota 2: Callback do Google (A URL que o Google usa para retornar)
@app.get("/auth/google/callback")
async def google_auth_callback(request: Request, db: Session = Depends(get_db)):
    """
    Recebe o código de autorização do Google, troca por um token e salva no DB.
    """
    try:
        # Pega a URL completa com os parâmetros que o Google adicionou (incluindo o 'code')
        full_url = str(request.url) 
        
        # O google_auth_flow_callback deve lidar com a troca do código pelo token
        token_info = google_auth_flow_callback(full_url)
        
        # Salva o token no banco de dados
        save_token(db, user_id=MAIN_USER_ID, token_json=json.dumps(token_info))
        
        # Retorna uma mensagem de sucesso para o usuário
        return HTMLResponse(
            content="<h1>✅ Autenticação Concluída com Sucesso!</h1><p>O Google Calendar está agora sincronizado com o seu bot do WhatsApp. Você pode fechar esta página.</p>",
            status_code=200
        )
        
    except Exception as e:
        print(f"Erro no callback do Google: {e}")
        return HTMLResponse(
            content=f"<h1>❌ Erro na Autenticação</h1><p>Ocorreu um problema ao salvar o token. Detalhe: {e}</p>",
            status_code=500
        )

# --- ROTAS DA APLICAÇÃO ---

# Rota para verificar se o servidor está funcionando
@app.get("/")
def read_root():
    return {"message": "Servidor está funcionando!"}

# Rota para processar mensagens do WhatsApp (Meta API)
@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        print(f"LOG ENTRADA: {json.dumps(data)}")

        # Meta WhatsApp envia as mensagens em um formato diferente
        message_text = data['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        from_number = data['entry'][0]['changes'][0]['value']['messages'][0]['from']

        # Processamento de IA
        ai_result: AgendaAction = process_message_with_ai(message_text)

        # Lógica de Ação
        response_message = ""

        # Verifique se o token do Google Calendar está disponível
        token_record = get_token(db, user_id=MAIN_USER_ID)
        google_token = json.loads(token_record.token_json) if token_record else None

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
                
                if google_token:
                    event_id = create_google_event(google_token, compromisso)
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
                    
                    if google_token and compromisso.google_event_id:
                        update_google_event(google_token, compromisso)
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
                    
                    if google_token and compromisso.google_event_id:
                        delete_google_event(google_token, compromisso.google_event_id)
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
        send_whatsapp_message(from_number, response_message)
        
        return {"status": "ok", "message": "Mensagem processada."}

    except Exception as e:
        # Caso haja algum erro
        import traceback
        error_detail = f"Erro no processamento da mensagem: {e}\n{traceback.format_exc()}"
        print(error_detail)
        
        # Tenta enviar a mensagem de erro, se o from_number estiver disponível
        try:
            from_number = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
            send_whatsapp_message(from_number, "Ocorreu um erro interno ao processar sua solicitação.")
        except:
            pass # Se não conseguir nem pegar o número, ignora.

        raise HTTPException(status_code=500, detail=str(e))
