# google_calendar_service.py - Versão Final Corrigida

import os
import json
import base64
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# --- Configuração ---
# O Render injeta o conteúdo do credentials.json codificado em Base64
CREDENTIALS_BASE64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
SCOPES = ['https://www.googleapis.com/auth/calendar']
REDIRECT_URI = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000" ) + "/auth/google/callback"

# Função auxiliar para carregar as credenciais do JSON (decodificando o Base64)
def load_credentials_info():
    if not CREDENTIALS_BASE64:
        raise ValueError("GOOGLE_CREDENTIALS_BASE64 environment variable not set.")
    
    # Decodifica o Base64 para obter o conteúdo do credentials.json
    credentials_json_bytes = base64.b64decode(CREDENTIALS_BASE64)
    credentials_info = json.loads(credentials_json_bytes.decode('utf-8'))
    
    # Extrai as informações necessárias para o Flow
    client_config = {
        "web": {
            "client_id": credentials_info["web"]["client_id"],
            "client_secret": credentials_info["web"]["client_secret"],
            "auth_uri": credentials_info["web"]["auth_uri"],
            "token_uri": credentials_info["web"]["token_uri"],
            "redirect_uris": [REDIRECT_URI]
        }
    }
    return client_config

# --- Funções de Autenticação (Faltantes) ---

def start_auth_flow():
    """Inicia o fluxo de autenticação OAuth 2.0 e retorna a URL de autorização."""
    client_config = load_credentials_info()
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    # O state é ignorado aqui, mas é importante em um fluxo real
    return authorization_url

def handle_auth_callback(code: str) -> str:
    """
    Troca o código de autorização por um token de acesso e retorna o token em formato JSON.
    """
    client_config = load_credentials_info()
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Troca o código pelo token
    flow.fetch_token(code=code)
    
    # Retorna o token em formato JSON (string)
    return flow.credentials.to_json()

# --- Funções de Serviço ---

def get_calendar_service(token_json: str):
    """Cria e retorna o objeto de serviço do Google Calendar."""
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    
    # Se o token expirou, tenta renová-lo
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    
    service = build('calendar', 'v3', credentials=creds)
    return service

# --- Funções de CRUD (Já estavam no seu código) ---

def create_google_event(token_json: str, compromisso):
    """Cria um evento no Google Calendar."""
    service = get_calendar_service(token_json)
    # ... (Sua lógica de criação de evento) ...
    return "google_event_id_placeholder" # Retorna o ID do evento criado

def update_google_event(token_json: str, compromisso):
    """Atualiza um evento no Google Calendar."""
    service = get_calendar_service(token_json)
    # ... (Sua lógica de atualização de evento) ...
    pass

def delete_google_event(token_json: str, google_event_id: str):
    """Deleta um evento no Google Calendar."""
    service = get_calendar_service(token_json)
    # ... (Sua lógica de exclusão de evento) ...
    pass

# --- Fim do google_calendar_service.py ---
