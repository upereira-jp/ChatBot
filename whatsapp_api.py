from twilio.rest import Client
import os

# Obtém as credenciais do Twilio através das variáveis de ambiente
TWILIO_ACCOUNT_SID = os.environ.get("ACe5d742a601be8a21319aeaedc49cc367")
TWILIO_AUTH_TOKEN = os.environ.get("5ed74083ed8dc84424e03a4ed5229ab1")
TWILIO_PHONE_NUMBER = os.environ.get("whatsapp: +14155238886")  # Número de WhatsApp do Twilio

# Certifique-se de que as variáveis de ambiente estão configuradas corretamente
if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    raise ValueError("Certifique-se de que todas as variáveis de ambiente do Twilio estão configuradas.")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_whatsapp_message(to: str, message: str):
    """Envia uma mensagem via WhatsApp usando o Twilio."""
    try:
        # Envia a mensagem para o número 'to' com o conteúdo 'message'
        message = client.messages.create(
            body=message,
            from_='whatsapp:' + TWILIO_PHONE_NUMBER,  # O número do Twilio
            to='whatsapp:' + to  # O número de destino do WhatsApp
        )
        print(f"Mensagem enviada para {to}: {message.sid}")
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
