import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Variáveis de ambiente para a API do WhatsApp
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

def send_whatsapp_message(to_number: str, message_body: str):
    """
    Envia uma mensagem de texto para um número de WhatsApp usando a Meta Cloud API.
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        print("ERRO: Variáveis de ambiente WHATSAPP_ACCESS_TOKEN ou WHATSAPP_PHONE_NUMBER_ID não configuradas.")
        return False

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": message_body
        }
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status() # Levanta exceção para códigos de status HTTP ruins (4xx ou 5xx)
        print(f"Mensagem enviada com sucesso para {to_number}. Resposta: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"ERRO ao enviar mensagem para {to_number}: {e}")
        return False

if __name__ == '__main__':
    # Exemplo de uso (requer variáveis de ambiente configuradas)
    # send_whatsapp_message("5511999999999", "Olá! Teste de envio de mensagem.")
    print("Módulo whatsapp_api.py pronto para uso.")
