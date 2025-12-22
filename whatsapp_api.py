import os
import requests
import json

# Variáveis de ambiente necessárias
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

def send_whatsapp_message(to_number: str, message_text: str):
    """
    Envia uma mensagem de texto simples via WhatsApp Business API.
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        print("ERRO: Variáveis de ambiente WHATSAPP_ACCESS_TOKEN ou WHATSAPP_PHONE_NUMBER_ID não configuradas.")
        return

    # Limpar o número de telefone para garantir que seja apenas dígitos
    clean_to_number = ''.join(filter(str.isdigit, to_number))
    
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_to_number,
        "type": "text",
        "text": {
            "body": message_text
        }
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload ))
        response.raise_for_status() # Levanta exceção para códigos de status HTTP ruins
        print(f"SUCESSO: Mensagem enviada para {clean_to_number}. Status: {response.status_code}")
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"ERRO HTTP ao enviar mensagem: {e}")
        print(f"Resposta do Meta: {response.text}")
    except Exception as e:
        print(f"ERRO ao enviar mensagem: {e}")
