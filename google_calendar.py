import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Se modificar estes escopos, delete o arquivo token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_google_calendar_service():
    """
    Realiza o fluxo de autenticação e retorna o objeto de serviço da Google Calendar API.
    O fluxo é projetado para ser executado uma vez para gerar o token.json.
    """
    creds = None
    token_file = os.getenv("TOKEN_FILE", "token.json")
    credentials_file = os.getenv("CREDENTIALS_FILE", "credentials.json")

    # O arquivo token.json armazena os tokens de acesso e refresh do usuário,
    # e é criado automaticamente quando o fluxo de autorização é concluído pela primeira vez.
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # Se não houver credenciais válidas, ou se o token expirou, inicia o fluxo de login.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # O arquivo credentials.json deve ser fornecido pelo usuário,
            # baixado do Google Cloud Console.
            if not os.path.exists(credentials_file):
                print(f"ERRO: Arquivo de credenciais não encontrado em {credentials_file}")
                print("Por favor, siga as instruções para obter o arquivo credentials.json.")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES
            )
            # O fluxo de autenticação deve ser feito manualmente pelo usuário,
            # pois requer interação com o navegador.
            print("\n--- INSTRUÇÕES DE AUTENTICAÇÃO DO GOOGLE CALENDAR ---")
            print("1. Execute este script em um ambiente que permita a abertura de um navegador.")
            print("2. Siga as instruções no console para abrir o link de autorização.")
            print("3. Autorize o acesso e cole o código de verificação de volta no console.")
            print("------------------------------------------------------\n")
            
            # Para um ambiente de servidor (como o sandbox), o fluxo de console é mais adequado.
            # No entanto, para o usuário final, precisaremos de um fluxo web.
            # Por enquanto, vamos simular o fluxo de console para gerar o token.
            # O usuário precisará executar esta parte manualmente ou fornecer o token.json.
            # Para o contexto do sandbox, vamos apenas retornar None e instruir o usuário.
            return None

        # Salva as credenciais para a próxima execução
        with open(token_file, "w") as token:
            token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)
        return service
    except HttpError as error:
        print(f"Ocorreu um erro ao construir o serviço do Google Calendar: {error}")
        return None

def create_event(service, summary, start_time, end_time, description=None, recurrence=None):
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
    
    if recurrence:
        event['recurrence'] = recurrence

    try:
        event = service.events().insert(calendarId='primary', body=event).execute()
        return event
    except HttpError as error:
        print(f"Ocorreu um erro ao criar o evento: {error}")
        return None

# Outras funções (get_events, update_event, delete_event) serão adicionadas conforme necessário.

if __name__ == '__main__':
    # Este bloco é apenas para testar a autenticação
    service = get_google_calendar_service()
    if service:
        print("Serviço do Google Calendar autenticado com sucesso!")
    else:
        print("Falha na autenticação do Google Calendar. Verifique as instruções.")
