# google_calendar_service.py — versão limpa (U+00A0 removido, indentação normalizada)

import os
import json
import base64
from datetime import timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ======================
# CONFIGURAÇÃO
# ======================

# Credenciais do Google em Base64 (Render / ENV)
CREDENTIALS_BASE64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")

# Escopos necessários
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# URL de redirecionamento
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000")
if RENDER_URL.endswith("/"):
    RENDER_URL = RENDER_URL[:-1]

REDIRECT_URI = f"{RENDER_URL}/auth/google/callback"


# ======================
# FUNÇÕES AUXILIARES
# ======================

def load_client_config() -> dict:
    """
    Decodifica as credenciais do Google a partir da variável de ambiente
    GOOGLE_CREDENTIALS_BASE64.
    """
    if not CREDENTIALS_BASE64:
        raise ValueError(
            "A variável de ambiente GOOGLE_CREDENTIALS_BASE64 não está definida."
        )

    try:
        credentials_json_bytes = base64.b64decode(CREDENTIALS_BASE64)
        credentials_info = json.loads(credentials_json_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(
            f"Erro ao decodificar GOOGLE_CREDENTIALS_BASE64: {e}"
        )

    return {
        "web": {
            "client_id": credentials_info["web"]["client_id"],
            "client_secret": credentials_info["web"]["client_secret"],
            "auth_uri": credentials_info["web"]["auth_uri"],
            "token_uri": credentials_info["web"]["token_uri"],
            "redirect_uris": [REDIRECT_URI],
        }
    }


# ======================
# AUTENTICAÇÃO OAUTH
# ======================

def start_auth_flow() -> str:
    """Inicia o fluxo OAuth 2.0 e retorna a URL de autorização."""
    client_config = load_client_config()

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    auth_url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
    )

    return auth_url


def handle_auth_callback(code: str) -> str:
    """Troca o código de autorização por um token OAuth."""
    client_config = load_client_config()

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    flow.fetch_token(code=code)
    return flow.credentials.to_json()


# Aliases de compatibilidade com o main.py
google_auth_flow_start = start_auth_flow
google_auth_flow_callback = handle_auth_callback


# ======================
# SERVIÇO DO CALENDAR
# ======================

def get_calendar_service(token_json: str):
    """
    Reconstrói as credenciais OAuth a partir do token salvo no banco
    e retorna o serviço do Google Calendar.
    """
    if not token_json:
        return None

    try:
        creds_dict = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return build("calendar", "v3", credentials=creds)

    except Exception as e:
        print(f"Erro ao criar serviço do Calendar: {e}")
        return None


# ======================
# CRUD DE EVENTOS
# ======================

# OBS: 'compromisso' não é tipado explicitamente
# para evitar importação circular com database.py

def create_google_event(token_json: str, compromisso):
    service = get_calendar_service(token_json)
    if not service:
        return None

    try:
        start_time = compromisso.data_hora
        duracao = getattr(compromisso, "duracao", 60) or 60
        end_time = start_time + timedelta(minutes=duracao)

        event_body = {
            "summary": compromisso.titulo,
            "description": f"{compromisso.assunto}\n\nAgendado via Bot.",
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
        }

        event = (
            service.events()
            .insert(calendarId="primary", body=event_body)
            .execute()
        )

        return event.get("id")

    except Exception as e:
        print(f"Erro create_google_event: {e}")
        return None


def update_google_event(token_json: str, compromisso) -> None:
    google_event_id = getattr(compromisso, "google_event_id", None)
    if not google_event_id:
        return

    service = get_calendar_service(token_json)
    if not service:
        return

    try:
        event = service.events().get(
            calendarId="primary", eventId=google_event_id
        ).execute()

        start_time = compromisso.data_hora
        duracao = getattr(compromisso, "duracao", 60) or 60
        end_time = start_time + timedelta(minutes=duracao)

        event["summary"] = compromisso.titulo
        event["start"]["dateTime"] = start_time.isoformat()
        event["end"]["dateTime"] = end_time.isoformat()

        service.events().update(
            calendarId="primary",
            eventId=google_event_id,
            body=event,
        ).execute()

    except Exception as e:
        print(f"Erro update_google_event: {e}")


def delete_google_event(token_json: str, google_event_id: str) -> None:
    if not google_event_id:
        return

    service = get_calendar_service(token_json)
    if not service:
        return

    try:
        service.events().delete(
            calendarId="primary", eventId=google_event_id
        ).execute()
    except Exception as e:
        print(f"Erro delete_google_event: {e}")
