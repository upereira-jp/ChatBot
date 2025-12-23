import os
import json
import base64
from datetime import timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# --- Configuração ---

# O Render injeta o conteúdo do credentials.json codificado em Base64
CREDENTIALS_BASE64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")

# Escopos necessários
SCOPES = ['https://www.googleapis.com/auth/calendar']

# URL de redirecionamento
# Tenta pegar a URL do Render, se não tiver, usa localhost (desenvolvimento )
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000" )
if RENDER_URL.endswith('/'):
    RENDER_URL = RENDER_URL[:-1]
REDIRECT_URI = f"{RENDER_URL}/auth/google/callback"

# --- Funções Auxiliares ---

def load_client_config():
    """Decodifica as credenciais do Google da variável de ambiente."""
    if not CREDENTIALS_BASE64:
        raise ValueError("A variável de ambiente GOOGLE_CREDENTIALS_BASE64 não está definida.")
    
    try:
        credentials_json_bytes = base64.b64decode(CREDENTIALS_BASE64)
        credentials_info = json.loads(credentials_json_bytes)
    except Exception as e:
        raise ValueError(f"Erro ao decodificar GOOGLE_CREDENTIALS_BASE64: {e}")

    # O google_auth_oauthlib.flow.Flow.from_client_config espera um dicionário
    # com a chave 'web' ou 'installed' no topo.
    client_config = {
        "web": {
            "client_id": credentials_info["web"]["client_id"],
            "client_secret": credentials_info["web"]["client_secret"],
            "auth_uri": credentials_info["web"]["auth_uri"],
            "token_uri": credentials_info["web"]["token_uri"],
            "redirect_uris": [REDIRECT_URI]
        }
    }
    
    # Log de depuração para verificar se as credenciais estão sendo lidas
    print(f"LOG (Debug Auth): Client ID: {client_config['web']['client_id']}", flush=True)
    print(f"LOG (Debug Auth): Redirect URI: {REDIRECT_URI}", flush=True)
    
    return client_config

def get_calendar_service(token_json: str):
    """Cria e retorna o objeto de serviço do Google Calendar."""
    if not token_json:
        return None
    
    try:
        # O token_json é a string JSON salva no banco de dados.
        # Precisamos desserializar para um dicionário para criar o objeto Credentials.
        token_info = json.loads(token_json)
        
        # Cria o objeto Credentials
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        
        # Se o token for inválido ou expirar, tenta renovar
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            
        # Constrói o serviço
        service = build('calendar', 'v3', credentials=creds)
        return service
        
    except Exception as e:
        print(f"Erro ao criar serviço do Calendar: {e}", flush=True)
        return None

# --- Funções de Autenticação ---

def google_auth_flow_start():
    """Inicia o fluxo de autenticação OAuth2."""
    client_config = load_client_config()
    flow = Flow.from_client_config(
        client_config, 
        scopes=SCOPES, 
        redirect_uri=REDIRECT_URI
    )
    
    # Adiciona prompt='consent' para forçar o envio do refresh_token
    auth_url, state = flow.authorization_url(
        access_type='offline', 
        include_granted_scopes='true',
        prompt='consent' # Força o consentimento para obter o refresh_token
    )
    return auth_url, state

def google_auth_flow_callback(full_url: str) -> str:
    """Completa o fluxo de autenticação e retorna o token JSON."""
    client_config = load_client_config()
    flow = Flow.from_client_config(
        client_config, 
        scopes=SCOPES, 
        redirect_uri=REDIRECT_URI
    )
    
    # Troca o código de autorização por um token
    flow.fetch_token(authorization_response=full_url)
    
    # Retorna o token como uma string JSON
    return flow.credentials.to_json()

# --- Funções de CRUD do Calendar ---

# Em google_calendar_service.py

def create_google_event(token_json: str, compromisso):
    service = get_calendar_service(token_json)
    if not service:
        return None

    try:
        start_time = compromisso.data_hora
        duracao = getattr(compromisso, 'duracao', 60) or 60
        end_time = start_time + timedelta(minutes=duracao)

        # --- CORREÇÃO DE FUSO HORÁRIO ---
        # Removemos a informação de timezone do objeto datetime (tornando-o naive)
        # e deixamos o campo 'timeZone' do payload controlar a localização.
        start_iso = start_time.replace(tzinfo=None).isoformat()
        end_iso = end_time.replace(tzinfo=None).isoformat()

        event_body = {
            'summary': compromisso.titulo,
            'location': 'Online',
            'description': compromisso.assunto,
            'start': {
                'dateTime': start_iso, 
                'timeZone': 'America/Sao_Paulo', 
            },
            'end': {
                'dateTime': end_iso,
                'timeZone': 'America/Sao_Paulo',
            },
            'reminders': {
                'useDefault': True,
            },
        }

        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return event.get('id')
    except Exception as e:
        print(f"Erro create_google_event: {e}", flush=True)
        return None

def update_google_event(token_json: str, compromisso):
    if not getattr(compromisso, 'google_event_id', None):
        return

    service = get_calendar_service(token_json)
    if not service:
        return

    try:
        # Pega o evento atual
        event = service.events().get(calendarId='primary', eventId=compromisso.google_event_id).execute()

        start_time = compromisso.data_hora
        duracao = getattr(compromisso, 'duracao', 60) or 60
        end_time = start_time + timedelta(minutes=duracao)

        event['summary'] = compromisso.titulo
        event['start']['dateTime'] = start_time.isoformat()
        event['end']['dateTime'] = end_time.isoformat()
        
        # Garante que o fuso horário seja mantido
        event['start']['timeZone'] = 'America/Sao_Paulo'
        event['end']['timeZone'] = 'America/Sao_Paulo'

        service.events().update(
            calendarId='primary', 
            eventId=compromisso.google_event_id, 
            body=event
        ).execute()
    except Exception as e:
        print(f"Erro update_google_event: {e}", flush=True)

def delete_google_event(token_json: str, google_event_id: str):
    if not google_event_id:
        return
    service = get_calendar_service(token_json)
    if not service:
        return
    try:
        service.events().delete(calendarId='primary', eventId=google_event_id).execute()
    except Exception as e:
        print(f"Erro delete_google_event: {e}", flush=True)
