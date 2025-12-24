import os
import requests
import json

# --- Configurações via Variáveis de Ambiente ---
# No Render, você configurará estas chaves
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERSION = "v21.0" # Versão atual da API da Meta

def send_whatsapp_message(to_number: str, message_body: str):
    """
    Envia uma mensagem de texto simples via WhatsApp Business API.
    """
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERRO: WHATSAPP_TOKEN ou PHONE_NUMBER_ID não configurados.", flush=True)
        return False

    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
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
        response = requests.post(url, headers=headers, json=payload)
        response_data = response.json()
        
        if response.status_code == 200:
            print(f"LOG (WhatsApp): Mensagem enviada com sucesso para {to_number}", flush=True)
            return True
        else:
            print(f"LOG (WhatsApp Erro): {json.dumps(response_data)}", flush=True)
            return False
            
    except Exception as e:
        print(f"LOG (WhatsApp Exception): {e}", flush=True)
        return False
