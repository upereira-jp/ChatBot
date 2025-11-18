import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# Se modificar estes escopos, delete o arquivo token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# O caminho para o arquivo JSON de credenciais do Google Cloud
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
# O caminho para o arquivo que armazenará o token de acesso do usuário
TOKEN_FILE = os.getenv("TOKEN_FILE", "token.json")

def get_google_calendar_service():
    """
    Retorna o objeto de serviço da Google Calendar API.
    Se o token não existir ou estiver expirado, retorna None.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Salva as credenciais atualizadas
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
        else:
            return None # Não autenticado
    
    try:
        service = build("calendar", "v3", credentials=creds)
        return service
    except Exception as error:
        print(f"Ocorreu um erro ao construir o serviço do Google Calendar: {error}")
        return None

def start_auth_flow(redirect_uri: str):
    """
    Inicia o fluxo de autenticação OAuth 2.0 e retorna a URL de autorização.
    """
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(f"Arquivo de credenciais não encontrado em {CREDENTIALS_FILE}. Por favor, forneça o arquivo.")

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, 
        scopes=SCOPES, 
        redirect_uri=redirect_uri
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    return authorization_url, state

def finish_auth_flow(authorization_response: str, redirect_uri: str):
    """
    Finaliza o fluxo de autenticação e salva o token.
    """
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, 
        scopes=SCOPES, 
        redirect_uri=redirect_uri
    )
    
    flow.fetch_token(authorization_response=authorization_response)
    
    creds = flow.credentials
    
    # Salva as credenciais para a próxima execução
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
        
    return creds.token is not None

from googleapiclient.errors import HttpError

def create_google_event(service, summary, start_time, end_time, description=None, recurrence=None):
    """Cria um evento no Google Calendar."""
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time,
            'timeZone': 'America/Sao_Paulo', # Assumindo fuso horário de SP para o Brasil
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'America/Sao_Paulo',
        },
    }
    
    if recurrence and recurrence != "NONE":
        # A API do Google usa o formato RRULE, que é mais complexo.
        # Por enquanto, vamos suportar apenas a criação simples.
        # A lógica de conversão de 'DAILY', 'WEEKLY' para RRULE é complexa e será simplificada.
        # Exemplo: 'RRULE:FREQ=WEEKLY;COUNT=10'
        pass

    try:
        event = service.events().insert(calendarId='primary', body=event).execute()
        return event.get('id')
    except HttpError as error:
        print(f"Ocorreu um erro ao criar o evento no Google Calendar: {error}")
        return None

def update_google_event(service, event_id, summary=None, start_time=None, end_time=None, description=None, recurrence=None):
    """Atualiza um evento existente no Google Calendar."""
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
        if summary: event['summary'] = summary
        if description: event['description'] = description
        if start_time: event['start']['dateTime'] = start_time
        if end_time: event['end']['dateTime'] = end_time
        
        # Lógica de recorrência mais complexa omitida por enquanto
        
        updated_event = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        return updated_event.get('id')
    except HttpError as error:
        print(f"Ocorreu um erro ao atualizar o evento no Google Calendar: {error}")
        return None

def delete_google_event(service, event_id):
    """Exclui um evento do Google Calendar."""
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return True
    except HttpError as error:
        print(f"Ocorreu um erro ao excluir o evento no Google Calendar: {error}")
        return False
