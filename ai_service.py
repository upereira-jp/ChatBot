import os
import json
from datetime import datetime
from openai import OpenAI
from pytz import timezone

# Configura o cliente OpenAI
# Certifique-se de ter a variável OPENAI_API_KEY no seu .env ou ambiente
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def get_ai_response(message_text: str):
    """
    Processa a mensagem do usuário usando GPT-4o-mini para extrair intenção de agendamento.
    """
    
    # Pegamos o horário atual de Goiânia para dar contexto à IA
    tz = timezone('America/Sao_Paulo')
    now = datetime.now(tz)
    current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    weekday_str = now.strftime("%A") # Dia da semana ajuda em "na próxima terça"

    system_prompt = f"""
    Você é uma assistente de agendamento executiva chamada 'Secretária'.
    
    CONTEXTO ATUAL:
    - Hoje é: {weekday_str}, {current_time_str} (Horário de Brasília/Goiânia).
    - O usuário está enviando uma mensagem via WhatsApp.
    
    FORMATO DE RESPOSTA (JSON APENAS):
    {{
      "action": "agendar",
      "titulo": "Reunião de Vendas",
      "data_hora": "2023-10-27T14:30:00",
      "assunto": "Detalhes extraídos da mensagem...",
      "duracao": 60,
      "resposta_whatsapp": "Texto curto e simpático confirmando o que entendeu para enviar ao usuário."
    }}
    
    Se faltar data/hora para agendar, action="erro" e peça a data no campo 'resposta_whatsapp'.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Modelo mais barato e rápido
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message_text}
            ],
            response_format={"type": "json_object"}, # Força saída JSON garantida
            temperature=0.0 # Zero criatividade, foco em precisão
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        print(f"Erro na IA: {e}")
        # Fallback de erro
        return {
            "action": "erro",
            "resposta_whatsapp": "Tive um problema técnico ao processar seu pedido. Tente novamente."
        }
      
