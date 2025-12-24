from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session
import json
import os
import re
import traceback
from datetime import datetime, time, date, timedelta
from pytz import timezone # Para lidar com fuso horário
import ai_service
# --- SUAS IMPORTAÇÕES DE MÓDULOS LOCAIS ---
from whatsapp_api import send_whatsapp_message 
import database 
import google_calendar_service 

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

try:
    print("Verificando/Criando tabelas no banco de dados...")
    database.Base.metadata.create_all(bind=database.engine)
    print("Tabelas prontas para uso!")
except Exception as e:
    print(f"Erro ao criar tabelas: {e}")

# --- CLASSE DE AÇÃO (Substitui o Mock) ---
class AgendaAction:
    """Estrutura de dados para a ação de agendamento."""
    def __init__(self, action, titulo, data_hora, assunto, duracao=60, recorrencia=None, id_compromisso=None):
        self.action = action
        self.titulo = titulo
        self.data_hora = data_hora
        self.assunto = assunto
        self.duracao = duracao
        self.recorrencia = recorrencia
        self.id_compromisso = id_compromisso

# --- PARSER SIMPLES (Substitui o Mock da IA) ---
def simple_nlp_parser(message_text: str) -> AgendaAction:
    """
    Parser melhorado com Regex para extrair horário e limpar o título.
    """
    tz = timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    target_date = agora

    # 1. Tenta encontrar padrões de hora (ex: 14h, 14:00, 14h30)
    # Regex procura por digitos seguidos de h ou :
    time_pattern = re.search(r'\b(\d{1,2})(?:h|:)(\d{2})?\b', message_text, re.IGNORECASE)
    
    nova_hora = agora.hour
    novo_minuto = agora.minute
    
    clean_text = message_text

    if time_pattern:
        # Extrai hora e minuto encontrados
        hora_str = time_pattern.group(1)
        minuto_str = time_pattern.group(2) or "00"
        
        try:
            nova_hora = int(hora_str)
            novo_minuto = int(minuto_str)
            
            # Ajuste básico: Se a hora solicitada já passou hoje, assume que é amanhã
            # (Ex: são 15h e usuário pede "reunião às 10h", joga para amanhã)
            if nova_hora < agora.hour or (nova_hora == agora.hour and novo_minuto < agora.minute):
                target_date = agora + timedelta(days=1)
            
            # Remove o horário do texto para limpar o título
            # Removemos o trecho encontrado (ex: "14h") da string original
            clean_text = message_text.replace(time_pattern.group(0), "").strip()
            
            # Remove palavras de ligação soltas que podem ter sobrado (ex: "Reunião às")
            clean_text = re.sub(r'\b(às|as|h)\b', '', clean_text, flags=re.IGNORECASE).strip()
            # Remove espaços duplos
            clean_text = re.sub(r'\s+', ' ', clean_text)

        except ValueError:
            pass # Se der erro na conversão, mantém horário atual

    # Atualiza o objeto de data com a hora encontrada
    final_datetime = target_date.replace(hour=nova_hora, minute=novo_minuto, second=0, microsecond=0)

    # 2. Definição do Título
    # Se depois da limpeza não sobrou nada, usa um padrão.
    titulo = clean_text if clean_text else "Nova Reunião"
    
    # Capitaliza a primeira letra
    titulo = titulo[0].upper() + titulo[1:] if titulo else titulo

    return AgendaAction(
        action="agendar",
        titulo=titulo,
        data_hora=final_datetime,
        assunto=f"Original: {message_text}", # Guarda a msg original na descrição
        duracao=60,
        recorrencia=None,
        id_compromisso=None
    )
# --- FIM DO PARSER SIMPLES ---

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
    Função processa a lógica de negócios real usando IA (OpenAI), 
    DB local e sincronização com Google Calendar.
    """
    try:
        print(f"LOG PAYLOAD (Background): {json.dumps(data)}", flush=True)

        # 1. Verificação de Payload do WhatsApp
        value = data['entry'][0]['changes'][0]['value']
        if not value.get('messages'):
            print("LOG (Background): Evento de status recebido. Ignorando.", flush=True)
            return

        # 2. Extração de dados básicos
        message_data = value['messages'][0]
        message_text = message_data['text']['body']
        from_number = message_data['from']

        # 3. Processamento de IA (Chamada ao ai_service que criamos)
        # Importante: certifique-se de ter 'import ai_service' no topo do seu main.py
        import ai_service
        ai_result = ai_service.get_ai_response(message_text)
        
        action = ai_result.get("action")
        # A IA já sugere uma resposta educada e direta no campo 'resposta_whatsapp'
        response_message = ai_result.get("resposta_whatsapp", "Processando sua solicitação...")

        # 4. Recuperação de credenciais do Google
        token_record = get_token(db, user_id=MAIN_USER_ID)
        google_token_json = token_record.token_json if token_record else None

        # 5. Execução da Lógica de Negócio baseada na decisão da IA
        
        if action == "agendar":
            data_iso = ai_result.get("data_hora")
            if not data_iso:
                # Caso a IA não tenha conseguido extrair a data, a resposta já pedirá os dados.
                pass 
            else:
                # Converte o ISO da IA para objeto datetime para o banco de dados
                dt_obj = datetime.fromisoformat(data_iso)
                
                compromisso = create_compromisso(
                    db,
                    titulo=ai_result.get("titulo"),
                    data_hora=dt_obj,
                    assunto=ai_result.get("assunto"),
                    duracao=ai_result.get("duracao", 60)
                )

                if google_token_json:
                    event_id = google_calendar_service.create_google_event(google_token_json, compromisso)
                    if event_id:
                        update_compromisso(db, compromisso.id, {"google_event_id": event_id})
                else:
                    response_message += "\n\n⚠️ O Google Calendar não está sincronizado."

        elif action == "reagendar":
            id_comp = ai_result.get("id_compromisso")
            data_iso = ai_result.get("data_hora")
            
            if id_comp and data_iso:
                dt_obj = datetime.fromisoformat(data_iso)
                compromisso = get_compromisso_por_id(db, id_comp)
                if compromisso:
                    update_compromisso(db, compromisso.id, {"data_hora": dt_obj})
                    if google_token_json and compromisso.google_event_id:
                        google_calendar_service.update_google_event(google_token_json, compromisso)

        elif action == "cancelar":
            id_comp = ai_result.get("id_compromisso")
            if id_comp:
                compromisso = get_compromisso_por_id(db, id_comp)
                if compromisso:
                    if google_token_json and compromisso.google_event_id:
                        google_calendar_service.delete_google_event(google_token_json, compromisso.google_event_id)
                    delete_compromisso(db, compromisso.id)

        elif action == "consultar":
            # Para consultas, usamos a data que a IA identificou ou hoje
            data_iso = ai_result.get("data_hora")
            dt_consulta = datetime.fromisoformat(data_iso).date() if data_iso else datetime.now().date()
            
            compromissos = get_compromissos_do_dia(db, datetime.combine(dt_consulta, datetime.min.time()))
            if compromissos:
                lista = "\n".join([f"- ID {c.id}: {c.titulo} às {c.data_hora.strftime('%H:%M')}" for c in compromissos])
                response_message = f"Agenda para {dt_consulta.strftime('%d/%m/%Y')}:\n{lista}"
            else:
                response_message = f"Não encontrei compromissos para {dt_consulta.strftime('%d/%m/%Y')}."

        # 6. Envio da Resposta Final via WhatsApp
        send_whatsapp_message(from_number, response_message)
        print(f"LOG (WhatsApp Send): Resposta enviada para {from_number}", flush=True)

    except Exception as e:
        error_detail = f"Erro no processamento da mensagem: {e}\n{traceback.format_exc()}"
        print(error_detail, flush=True)
        try:
            # Tenta avisar o usuário do erro técnico
            from_number = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
            send_whatsapp_message(from_number, "Desculpe, tive um problema ao processar isso agora. Pode repetir?")
        except:
            pass

@app.get("/privacidade", response_class=HTMLResponse)
async def privacidade():
    """
    Retorna a página de Política de Privacidade formatada em HTML.
    Esta URL deve ser inserida no painel do Meta Developers.
    """
    content = """
    <!DOCTYPE html>
    <html lang="pt-br">
        <head>
            <meta charset="UTF-8">
            <title>Política de Privacidade - Alfred</title>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; padding: 40px; line-height: 1.6; max-width: 800px; margin: auto; color: #333; }
                h1 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }
                h2 { color: #2c3e50; margin-top: 30px; }
                p { margin-bottom: 15px; text-align: justify; }
                ul { margin-bottom: 15px; }
                .footer { margin-top: 50px; font-size: 0.9em; color: #7f8c8d; border-top: 1px solid #eee; pt: 20px; }
            </style>
        </head>
        <body>
            <h1>Política de Privacidade</h1>
            <p><strong>Última atualização: 24/12/2025</strong></p>
            
            <p>A sua privacidade é importante para nós. É política do <strong>Alfred</strong> respeitar a sua privacidade em relação a qualquer informação sua que possamos coletar no serviço Alfred, e outros sites que possuímos e operamos.</p>

            <p>Solicitamos informações pessoais apenas quando realmente precisamos delas para lhe fornecer um serviço, como a integração com o <strong>Google Calendar</strong> e <strong>WhatsApp Business API</strong>. Fazemo-lo por meios justos e legais, com o seu conhecimento e consentimento. Também informamos por que estamos coletando e como será usado.</p>

            <p>Apenas retemos as informações coletadas pelo tempo necessário para fornecer o serviço solicitado. Quando armazenamos dados (como tokens de acesso), protegemos dentro de meios comercialmente aceitáveis para evitar perdas e roubos, bem como acesso, divulgação, cópia, uso ou modificação não autorizados.</p>

            <p>Não compartilhamos informações de identificação pessoal publicamente ou com terceiros, exceto quando exigido por lei.</p>

            <h2>Compromisso do Usuário</h2>
            <p>O usuário se compromete a fazer uso adequado dos conteúdos e da informação que o Alfred oferece:</p>
            <ul>
                <li><strong>A)</strong> Não se envolver em atividades que sejam ilegais ou contrárias à boa fé;</li>
                <li><strong>B)</strong> Não causar danos aos sistemas físicos (hardwares) e lógicos (softwares) do Alfred;</li>
                <li><strong>C)</strong> Não disseminar vírus informáticos ou quaisquer outros sistemas que sejam capazes de causar danos.</li>
            </ul>

            <div class="footer">
                <p>Esta política é efetiva a partir de 24 de Dezembro de 2025.</p>
                <p>Contato: https://alfred-5klb.onrender.com</p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=content, status_code=200)

@app.get("/termos", response_class=HTMLResponse)
async def termos():
    """
    Retorna a página de Termos de Serviço formatada em HTML.
    Esta URL é necessária para a conformidade do app no Meta Developers.
    """
    content = """
    <!DOCTYPE html>
    <html lang="pt-br">
        <head>
            <meta charset="UTF-8">
            <title>Termos de Serviço - Alfred</title>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; padding: 40px; line-height: 1.6; max-width: 800px; margin: auto; color: #333; }
                h1 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }
                h2 { color: #2c3e50; margin-top: 30px; font-size: 1.4em; }
                p { margin-bottom: 15px; text-align: justify; }
                ol { margin-bottom: 15px; }
                li { margin-bottom: 10px; }
                .footer { margin-top: 50px; font-size: 0.9em; color: #7f8c8d; border-top: 1px solid #eee; padding-top: 20px; }
            </style>
        </head>
        <body>
            <h1>Termos de Serviço</h1>
            
            <h2>1. Termos</h2>
            <p>Ao acessar ao site <a href="https://alfred-5klb.onrender.com" style="color: #3498db; text-decoration: none;">Alfred</a>, concorda em cumprir estes termos de serviço, todas as leis e regulamentos aplicáveis e concorda que é responsável pelo cumprimento de todas as leis locais aplicáveis. Os materiais contidos neste site são protegidos pelas leis de direitos autorais e marcas comerciais aplicáveis.</p>

            <h2>2. Uso de Licença</h2>
            <p>É concedida permissão para baixar temporariamente uma cópia dos materiais (informações ou software) no site Alfred, apenas para visualização transitória pessoal e não comercial. Esta é a concessão de uma licença, não uma transferência de título e, sob esta licença, você não pode:</p>
            <ol>
                <li>Modificar ou copiar os materiais;</li>
                <li>Usar os materiais para qualquer finalidade comercial ou para exibição pública;</li>
                <li>Tentar descompilar ou fazer engenharia reversa de qualquer software contido no site Alfred;</li>
                <li>Remover quaisquer direitos autorais ou outras notações de propriedade;</li>
                <li>Transferir os materiais para outra pessoa ou 'espelhar' os materiais em outro servidor.</li>
            </ol>

            <h2>3. Isenção de Responsabilidade</h2>
            <p>Os materiais no site da Alfred são fornecidos 'como estão'. Alfred não oferece garantias, expressas ou implícitas, e, por este meio, isenta e nega todas as outras garantias, incluindo, sem limitação, condições de comercialização ou adequação a um fim específico.</p>

            <h2>4. Limitações</h2>
            <p>Em nenhum caso o Alfred ou seus fornecedores serão responsáveis por quaisquer danos (incluindo, sem limitação, danos por perda de dados ou lucro ou devido a interrupção dos negócios) decorrentes do uso ou da incapacidade de usar os materiais em Alfred.</p>

            <h2>5. Precisão dos Materiais</h2>
            <p>Os materiais exibidos no site da Alfred podem incluir erros técnicos, tipográficos ou fotográficos. Alfred não garante que qualquer material em seu site seja preciso, completo ou atual.</p>

            <h2>6. Links</h2>
            <p>O Alfred não analisou todos os sites vinculados ao seu site e não é responsável pelo conteúdo de nenhum site vinculado. O uso de qualquer site vinculado é por conta e risco do usuário.</p>

            <div class="footer">
                <p><strong>Modificações:</strong> O Alfred pode revisar estes termos a qualquer momento, sem aviso prévio. Ao usar este site, você concorda em ficar vinculado à versão atual desses termos de serviço.</p>
                <p><strong>Lei Aplicável:</strong> Estes termos são regidos pelas leis locais e você se submete à jurisdição exclusiva dos tribunais naquela localidade.</p>
                <p>Contato: blackhaus.com.br</p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=content, status_code=200)

# --- ROTAS DE AUTENTICAÇÃO DO GOOGLE CALENDAR ---

@app.get("/auth/google/start")
async def google_auth_start():
    try:
        auth_url, _ = google_auth_flow_start()
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
