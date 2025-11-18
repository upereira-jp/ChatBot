from fastapi import FastAPI, Request, HTTPException, Response
from datetime import datetime, timedelta
import json
from .nlp_processor import process_message_with_ai
from .google_calendar_service import start_auth_flow, finish_auth_flow, get_google_calendar_service, create_google_event, update_google_event, delete_google_event
from .database import initialize_db, save_compromisso, get_compromissos_by_day, update_compromisso, delete_compromisso, get_compromisso_by_id, get_compromissos_by_whatsapp_id
from .whatsapp_api import send_whatsapp_message
from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente
load_dotenv()

app = FastAPI(title="IA de Agenda via WhatsApp")

# Inicializa o banco de dados na inicialização do app
@app.on_event("startup")
def startup_event():
    initialize_db()

# --- Rotas de Autenticação e Webhooks ---

@app.get("/")
def read_root():
    return {"message": "Serviço de IA de Agenda via WhatsApp está rodando."}

# Rota para iniciar o fluxo de autenticação do Google Calendar (manual)
# --- Rotas de Autenticação e Webhooks ---

# Rota de Webhook do WhatsApp para verificação
@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
    
    # Parâmetros de consulta da Meta
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # Verifica se o token e o modo estão corretos
    if mode and token:
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return Response(content=challenge, media_type="text/plain")
        else:
            # Responde com '403 Forbidden' se os tokens não corresponderem
            raise HTTPException(status_code=403, detail="Verification token mismatch")
    
    raise HTTPException(status_code=400, detail="Missing parameters")

# Rota de Webhook do WhatsApp para recebimento de mensagens
@app.post("/webhook/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    data = await request.json()
    
    # Verifica se a notificação é de uma mensagem
    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "messages":
                    for message in change.get("value", {}).get("messages", []):
                        # Processa apenas mensagens de texto
                        if message.get("type") == "text":
                            from_number = message.get("from")
                            message_body = message.get("text", {}).get("body")
                            
                            print(f"Mensagem recebida de {from_number}: {message_body}")
                            
                            # Processamento com IA
                            try:
                                parsed_data = process_message_with_ai(message_body)
                                response_message = handle_agenda_action(from_number, parsed_data)
                            except Exception as e:
                                print(f"Erro no processamento da mensagem: {e}")
                                response_message = "Desculpe, não consegui processar sua solicitação. Por favor, tente de outra forma."
                                
                            # Envio da resposta
                            send_whatsapp_message(from_number, response_message)# --- Rotas de Autenticação Google Calendar (OAuth 2.0) ---

@app.get("/auth/google/start")
def google_auth_start(request: Request):
    # A URL de redirecionamento deve ser a URL pública do seu servidor + /auth/google/callback
    # No ambiente de produção, esta URL deve ser configurada no Google Cloud Console
    # No sandbox, usaremos a URL exposta
    base_url = str(request.base_url).replace("http://", "https://") # Força HTTPS
    redirect_uri = f"{base_url}auth/google/callback"
    
    try:
        authorization_url, state = start_auth_flow(redirect_uri)
        
        # O estado deve ser armazenado para verificação, mas para simplificar, vamos ignorar por enquanto
        # Em produção, você deve armazenar 'state' em uma sessão de usuário.
        
        return {"message": "Clique no link para autorizar o acesso à sua Google Agenda.", "url": authorization_url}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Arquivo de credenciais (credentials.json) não encontrado. Por favor, forneça o arquivo.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao iniciar o fluxo de autenticação: {e}")

@app.get("/auth/google/callback")
def google_auth_callback(request: Request):
    # A URL de redirecionamento deve ser a URL pública do seu servidor + /auth/google/callback
    base_url = str(request.base_url).replace("http://", "https://")
    redirect_uri = f"{base_url}auth/google/callback"
    
    try:
        # A resposta de autorização é a URL completa que o Google redireciona
        authorization_response = str(request.url)
        
        if finish_auth_flow(authorization_response, redirect_uri):
            return {"message": "Autenticação com o Google Calendar concluída com sucesso! Você pode fechar esta página."}
        else:
            return {"message": "Falha ao obter o token de acesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar o fluxo de autenticação: {e}")

# --- Lógica de Agenda (CRUD e Consulta) ---

def handle_agenda_action(whatsapp_id: str, data: dict) -> str:
    """
    Executa a ação de agenda com base nos dados extraídos pela IA.
    """
    acao = data.get("acao", "agendar").lower()
    
    if acao == "agendar":
        try:
            data_hora_inicio = datetime.strptime(f"{data['data']} {data['hora']}", "%Y-%m-%d %H:%M")
            
            # 1. Salvar no banco de dados interno
            compromisso = save_compromisso(
                whatsapp_id=whatsapp_id,
                titulo=data["titulo"],
                data_hora_inicio=data_hora_inicio,
                duracao_minutos=data["duracao_minutos"],
                assunto_servico=data["assunto_servico"],
                recorrencia=data["recorrencia"]
            )
            
            # 2. Sincronizar com o Google Calendar
            service = get_google_calendar_service()
            google_event_id = None
            if service:
                data_hora_fim = data_hora_inicio + timedelta(minutes=data["duracao_minutos"])
                google_event_id = create_google_event(
                    service,
                    summary=data["titulo"],
                    start_time=data_hora_inicio.isoformat(),
                    end_time=data_hora_fim.isoformat(),
                    description=f"Agendado via WhatsApp. Assunto/Serviço: {data['assunto_servico']}"
                )
                
                if google_event_id:
                    # Atualizar o compromisso interno com o ID do Google Calendar
                    update_compromisso(compromisso['id'], google_event_id=google_event_id)
                    return f"Compromisso agendado com sucesso! ID: {compromisso['id']}. Sincronizado com Google Agenda."
                else:
                    return f"Compromisso agendado localmente (ID: {compromisso['id']}), mas falhou a sincronização com Google Agenda. Verifique a autenticação."
            
            return f"Compromisso agendado com sucesso! ID: {compromisso['id']}. Título: {compromisso['titulo']} em {data_hora_inicio.strftime('%d/%m/%Y às %H:%M')}."
        except Exception as e:
            return f"Erro ao agendar: {e}. Verifique se a data e hora estão corretas."
            
    elif acao == "consultar":
        # Implementação simplificada para consultar o dia de hoje
        compromissos = get_compromissos_by_day(whatsapp_id, datetime.now().date())
        
        # Consultar também o Google Calendar (apenas para leitura, se autenticado)
        service = get_google_calendar_service()
        google_events = []
        if service:
            # Lógica para buscar eventos do Google Calendar para o dia
            now = datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
            events_result = service.events().list(calendarId='primary', timeMin=now,
                                                maxResults=10, singleEvents=True,
                                                orderBy='startTime').execute()
            google_events = events_result.get('items', [])
        
        if not compromissos and not google_events:
            return "Você não tem compromissos agendados para hoje."
            
        response = "Seus compromissos para hoje:\n"
        for c in compromissos:
            response += f"- ID {c['id']}: {c['titulo']} ({c['assunto_servico']}) às {datetime.fromisoformat(c['data_hora_inicio']).strftime('%H:%M')}\n"
            
        if google_events:
            response += "\nCompromissos do Google Agenda (próximos 10):\n"
            for event in google_events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                response += f"- {event['summary']} em {start}\n"
                
        return response
        
    elif acao == "cancelar" or acao == "excluir":
        id_compromisso = data.get("id_compromisso")
        if id_compromisso and id_compromisso != 0:
            try:
                compromisso = get_compromisso_by_id(id_compromisso)
                if not compromisso:
                    return f"Não foi possível encontrar o compromisso ID {id_compromisso}."
                    
                # 1. Cancelar no banco de dados interno
                update_compromisso(id_compromisso, status="cancelado")
                
                # 2. Sincronizar com o Google Calendar
                service = get_google_calendar_service()
                if service and compromisso.get('google_event_id'):
                    if delete_google_event(service, compromisso['google_event_id']):
                        return f"Compromisso ID {id_compromisso} cancelado com sucesso e removido do Google Agenda."
                    else:
                        return f"Compromisso ID {id_compromisso} cancelado localmente, mas falhou a remoção do Google Agenda."
                
                return f"Compromisso ID {id_compromisso} cancelado com sucesso."
            except Exception:
                return f"Não foi possível encontrar ou cancelar o compromisso ID {id_compromisso}."
        else:
            return "Por favor, forneça o ID do compromisso que deseja cancelar/excluir."
            
    elif acao == "reagendar":
        id_compromisso = data.get("id_compromisso")
        if id_compromisso and id_compromisso != 0:
            try:
                compromisso = get_compromisso_by_id(id_compromisso)
                if not compromisso:
                    return f"Não foi possível encontrar o compromisso ID {id_compromisso}."
                    
                nova_data_hora = datetime.strptime(f"{data['data']} {data['hora']}", "%Y-%m-%d %H:%M")
                nova_data_hora_fim = nova_data_hora + timedelta(minutes=data["duracao_minutos"])
                
                # 1. Reagendar no banco de dados interno
                update_compromisso(
                    id_compromisso, 
                    data_hora_inicio=nova_data_hora.isoformat(),
                    data_hora_fim=nova_data_hora_fim.isoformat()
                )
                
                # 2. Sincronizar com o Google Calendar
                service = get_google_calendar_service()
                if service and compromisso.get('google_event_id'):
                    google_event_id = update_google_event(
                        service, 
                        compromisso['google_event_id'],
                        start_time=nova_data_hora.isoformat(),
                        end_time=nova_data_hora_fim.isoformat()
                    )
                    if google_event_id:
                        return f"Compromisso ID {id_compromisso} reagendado para {nova_data_hora.strftime('%d/%m/%Y às %H:%M')} e sincronizado com Google Agenda."
                    else:
                        return f"Compromisso ID {id_compromisso} reagendado localmente, mas falhou a sincronização com Google Agenda."
                
                return f"Compromisso ID {id_compromisso} reagendado para {nova_data_hora.strftime('%d/%m/%Y às %H:%M')}."
            except Exception as e:
                return f"Erro ao reagendar: {e}. Verifique o ID, data e hora."
        else:
            return "Por favor, forneça o ID do compromisso que deseja reagendar."
            
    elif acao == "recorrencia":
        return "A funcionalidade de recorrência será implementada em uma versão futura."
        
    else:
        return "Ação não reconhecida. Tente 'agendar', 'consultar', 'reagendar' ou 'cancelar'."
if __name__ == "__main__":
    import uvicorn
    # O host '0.0.0.0' é necessário para que o servidor seja acessível externamente no sandbox
    uvicorn.run(app, host="0.0.0.0", port=8000)
