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
        credentials_info = json.loads(credentials_json_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Erro ao decodificar GOOGLE_CREDENTIALS_BASE64: {e}")
    
    client_config = {
        "web": {
            "client_id": credentials_info["web"]["client_id"],
            "client_secret": credentials_info["web"]["client_secret"],
            "auth_uri": credentials_info["web"]["auth_uri"],
            "token_uri": credentials_info["web"]["token_uri"],
            "redirect_uris": [REDIRECT_URI]
        }
    }
    
    # --- LOG DE DEBUG ---
    print(f"LOG (Debug Auth): Client ID: {client_config['web']['client_id']}", flush=True)
    print(f"LOG (Debug Auth): Redirect URI: {REDIRECT_URI}", flush=True)
    # --- FIM DO LOG ---
    
    return client_config

# --- 1. Funções de Autenticação ---

def start_auth_flow():
    """Inicia o fluxo de autenticação OAuth 2.0."""
    client_config = load_client_config()
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent' # CORREÇÃO: Força o refresh_token
    )
    return auth_url, state 

def handle_auth_callback(full_url: str) -> str: # CORREÇÃO: Recebe apenas a URL completa
    """Troca o código pelo token."""
    client_config = load_client_config()
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    # O full_url contém o code e o state
    flow.fetch_token(authorization_response=full_url)
    return flow.credentials.to_json()

# --- ALIASES DE COMPATIBILIDADE (Para corrigir o erro de importação) ---
# Isso garante que funcione tanto se o main.py pedir o nome novo quanto o antigo.
google_auth_flow_start = start_auth_flow
google_auth_flow_callback = handle_auth_callback


# --- 2. Função para Obter o Serviço ---

def get_calendar_service(token_json: str):
    """Reconstrói as credenciais e retorna o serviço."""
    if not token_json:
        return None
    try:
        # CORREÇÃO: O token_json vem do DB como string JSON. 
        # Ele precisa ser desserializado AQUI.
        creds_dict = json.loads(token_json)
        
        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"Erro ao criar serviço do Calendar: {e}")
        return None

# --- 3. Funções de CRUD ---

# ATENÇÃO: Os parâmetros 'compromisso' NÃO possuem tipagem explicita da classe
# para evitar o erro de Importação Circular com o database.py.

def create_google_event(token_json: str, compromisso):
    service = get_calendar_service(token_json)
    if not service:
        return None

    try:
        start_time = compromisso.data_hora
        duracao = getattr(compromisso, 'duracao', 60) or 60
        end_time = start_time + timedelta(minutes=duracao)

        event_body = {
            'summary': compromisso.titulo,
            'description': f"{compromisso.assunto}\n\nAgendado via Bot.",
            'start': {'dateTime': start_time.isoformat(), 'timeZone': 'America/Sao_Paulo'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'America/Sao_Paulo'},
        }

        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return event.get('id')
    except Exception as e:
        print(f"Erro create_google_event: {e}")
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

        service.events().update(
            calendarId='primary', 
            eventId=compromisso.google_event_id, 
            body=event
        ).execute()
    except Exception as e:
        print(f"Erro update_google_event: {e}")

def delete_google_event(token_json: str, google_event_id: str):
    if not google_event_id:
        return
    service = get_calendar_service(token_json)
    if not service:
        return
    try:
        service.events().delete(calendarId='primary', eventId=google_event_id).execute()
    except Exception as e:
        print(f"Erro delete_google_event: {e}")
