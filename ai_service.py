import os
import json
from datetime import datetime
from openai import OpenAI
from pytz import timezone

# Configura o cliente OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def get_ai_response(message_text: str):
    """
    Processa a mensagem do usuário usando GPT-4o-mini.
    """
    
    # Contexto Temporal (Crucial para a IA saber o que é "amanhã")
    tz = timezone('America/Sao_Paulo')
    now = datetime.now(tz)
    current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    weekday_str = now.strftime("%A") 

    system_prompt = f"""
    Você é a 'Secretária', uma assistente executiva da BlackHaus (imobiliária de alto padrão).
    
    CONTEXTO ATUAL:
    - Hoje é: {weekday_str}, {current_time_str} (Horário de Brasília/Goiânia).
    
    SUA PERSONALIDADE:
    - Seja eficiente, educada e direta.
    - Tenha um leve toque de humor ácido/irônico quando apropriado, mas nunca seja desrespeitosa.
    - Você resolve problemas, não cria novos.
    
    SUA MISSÃO:
    Analise a mensagem do usuário e extraia a intenção em JSON estrito.
    
    REGRAS DE EXTRAÇÃO:
    1. action: "agendar", "reagendar", "cancelar", "consultar" ou "conversa" (para papo furado).
    2. data_hora: Converta TUDO para ISO 8601 (YYYY-MM-DDTHH:MM:SS). Se o usuário disser "sexta", calcule a data baseada no dia de hoje ({weekday_str}).
    3. titulo: Resuma o pedido em 2 ou 3 palavras profissionais (ex: "Reunião Vendas").
    4. duracao: Padrão 60 min se não informado.
    5. resposta_whatsapp: Escreva a mensagem que será enviada de volta ao usuário. Deve confirmar a ação ou pedir o dado que falta.
    
    IMPORTANTE:
    - Se a action for "agendar" e faltar hora/data, mude action para "erro" e peça o dado faltante na 'resposta_whatsapp'.
    - Se for "consultar", a data_hora deve ser o dia que ele quer ver a agenda.
    
    EXEMPLO DE JSON DE RESPOSTA (Basta preencher os campos):
    {{
      "action": "agendar",
      "titulo": "Almoço Executivo",
      "data_hora": "2023-10-27T14:30:00",
      "assunto": "Tratar de negócios",
      "duracao": 60,
      "id_compromisso": null,
      "resposta_whatsapp": "Certo, marquei seu almoço. Tente não se atrasar."
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # CORRETO: Modelo mais rápido e barato
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message_text}
            ],
            response_format={"type": "json_object"}, # Garante que o Python não quebre
            temperature=0.2 # Baixa criatividade para garantir precisão nos dados
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        print(f"Erro na IA: {e}")
        return {
            "action": "erro",
            "resposta_whatsapp": "Ocorreu um erro técnico na minha conexão neural. Tente novamente em instantes."
        }
