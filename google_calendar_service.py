import os
import json
import base64
from datetime import timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# --- Configuração ---

# O Render injeta o conteúdo do credentials.json codificado em Base64 na variável de ambiente
CREDENTIALS_BASE64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")

# Escopos necessários para ler e escrever no calendário
SCOPES = ['https://www.googleapis.com/auth/calendar']

# URL de redirecionamento (Callback). 
# Em produção (Render), deve ser a URL da sua aplicação. Localmente, localhost.
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000")
# Remove barra no final se houver, para evitar urls duplas como //.com//auth
if RENDER_URL.endswith('/'):
    RENDER_URL = RENDER_URL[:-1]
REDIRECT_URI = f"{RENDER_URL}/auth/google/callback"

# --- Funções Auxiliares de Configuração ---

def load_client_config():
    """
    Decodifica as credenciais do Google (client_secret) da variável de ambiente Base64.
    Isso evita ter o arquivo físico client_secret.json no servidor.
    """
    if not CREDENTIALS_BASE64:
        raise ValueError("A variável de ambiente GOOGLE_CREDENTIALS_BASE64 não está definida.")
    
    # Decodifica o Base64 para obter o JSON string
    try:
        credentials_json_bytes = base64.b64decode(CREDENTIALS_BASE64)
        credentials_info = json.loads(credentials_json_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Erro ao decodificar GOOGLE_CREDENTIALS_BASE64: {e}")
    
    # Monta a configuração do cliente para o Flow
    return {
        "web": {
            "client_id": credentials_info["web"]["client_id"],
            "client_secret": credentials_info["web"]["client_secret"],
            "auth_uri": credentials_info["web"]["auth_uri"],
            "token_uri": credentials_info["web"]["token_uri"],
            "redirect_uris": [REDIRECT_URI]
        }
    }

# --- 1. Funções de Autenticação (OAuth 2.0) ---

def start_auth_flow():
    """
    Inicia o fluxo de autenticação e retorna a URL para onde o usuário deve ser redirecionado.
    """
    client_config = load_client_config()
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Gera a URL de autorização. 
    # access_type='offline' é crucial para receber um refresh_token
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    return authorization_url

def handle_auth_callback(code: str) -> str:
    """
    Recebe o código de autorização devolvido pelo Google, troca por tokens
    e retorna o JSON dos tokens como string.
    """
    client_config = load_client_config()
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Troca o código (code) pelos tokens de acesso e refresh
    flow.fetch_token(code=code)
    
    # Retorna as credenciais serializadas em JSON
    return flow.credentials.to_json()

# --- 2. Função para Obter o Serviço da API ---

def get_calendar_service(token_json: str):
    """
    Reconstrói as credenciais a partir do JSON salvo e retorna o serviço da API.
    Lida com a renovação automática do token se ele estiver expirado.
    """
    if not token_json:
        return None

    try:
        # Carrega as credenciais a partir da string JSON salva no banco
        creds_dict = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)
        
        # Verifica se o token expirou e tenta renovar
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Erro ao renovar token: {e}")
                return None

        # Constrói o serviço
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Erro ao criar serviço do Calendar: {e}")
        return None

# --- 3. Funções de CRUD (Create, Update, Delete) ---

# NOTA: O parâmetro 'compromisso' abaixo NÃO tem tipagem explícita da classe (ex: :Compromisso)
# para evitar a IMPORTAÇÃO CIRCULAR com database.py. O código assume que o objeto
# passado possui os atributos: titulo, assunto, data_hora, duracao, id, google_event_id.

def create_google_event(token_json: str, compromisso):
    """
    Cria um evento no Google Calendar.
    """
    service = get_calendar_service(token_json)
    if not service:
        print("Serviço do Google Calendar não disponível (Token inválido?).")
        return None

    try:
        # Define horário de início e fim
        start_time = compromisso.data_hora
        # Assume duração em minutos, padrão 60 se não houver
        duracao_minutos = getattr(compromisso, 'duracao', 60) or 60 
        end_time = start_time + timedelta(minutes=duracao_minutos)

        event_body = {
            'summary': compromisso.titulo,
            'description': f"{compromisso.assunto}\n\nAgendado via WhatsApp Bot.",
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/Sao_Paulo', # Ajuste seu fuso horário se necessário
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Sao_Paulo',
            },
        }

        event = service.events().insert(calendarId='primary', body=event_body).execute()
        print(f"Evento criado no Google Calendar: {event.get('htmlLink')}")
        return event.get('id')

    except Exception as e:
        print(f"Erro ao criar evento no Google Calendar: {e}")
        return None

def update_google_event(token_json: str, compromisso):
    """
    Atualiza um evento existente no Google Calendar.
    """
    if not compromisso.google_event_id:
        print("Compromisso não possui ID do Google Calendar para atualizar.")
        return

    service = get_calendar_service(token_json)
    if not service:
        return

    try:
        # Recupera o evento atual para não perder dados que não vamos mudar
        event = service.events().get(calendarId='primary', eventId=compromisso.google_event_id).execute()

        # Atualiza horários
        start_time = compromisso.data_hora
        duracao_minutos = getattr(compromisso, 'duracao', 60) or 60
        end_time = start_time + timedelta(minutes=duracao_minutos)

        event['summary'] = compromisso.titulo
        event['description'] = f"{compromisso.assunto}\n\nAgendado via WhatsApp Bot (Atualizado)."
        event['start']['dateTime'] = start_time.isoformat()
        event['end']['dateTime'] = end_time.isoformat()

        updated_event = service.events().update(
            calendarId='primary', 
            eventId=compromisso.google_event_id, 
            body=event
        ).execute()
        
        print(f"Evento atualizado no Google Calendar: {updated_event.get('htmlLink')}")

    except Exception as e:
        print(f"Erro ao atualizar evento no Google Calendar: {e}")

def delete_google_event(token_json: str, google_event_id: str):
    """
    Deleta um evento do Google Calendar.
    """
    if not google_event_id:
        return

    service = get_calendar_service(token_json)
    if not service:
        return

    try:
        service.events().delete(calendarId='primary', eventId=google_event_id).execute()
        print(f"Evento {google_event_id} deletado do Google Calendar.")
    except Exception as e:
        print(f"Erro ao deletar evento no Google Calendar: {e}")
