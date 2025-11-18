import os
import json
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from datetime import datetime

# Configuração do cliente OpenAI (usará a variável de ambiente OPENAI_API_KEY)
client = OpenAI()

# 1. Definir o Schema de Saída para o Agendamento
class AgendamentoSchema(BaseModel):
    """Schema para extrair informações de agendamento de texto livre."""
    acao: str = Field(description="Ação desejada: 'agendar', 'reagendar', 'cancelar', 'consultar', 'recorrencia', 'excluir'.")
    titulo: str = Field(description="Descrição/título do evento/compromisso/tarefa. Deve ser conciso.")
    data: str = Field(description="Data do compromisso no formato YYYY-MM-DD. Se não especificada, use a data de hoje.")
    hora: str = Field(description="Hora do compromisso no formato HH:MM. Se não especificada, use '09:00'.")
    assunto_servico: str = Field(description="Assunto ou serviço relacionado ao compromisso.")
    duracao_minutos: int = Field(description="Duração do compromisso em minutos. Se não especificada, use 60.")
    recorrencia: str = Field(description="Regra de recorrência (ex: 'DAILY', 'WEEKLY', 'MONTHLY'). Se não especificada, use 'NONE'.")
    id_compromisso: int = Field(description="ID do compromisso a ser modificado (para reagendar, cancelar ou excluir). Use 0 se for um novo agendamento.")

# 2. Definir a Função de Processamento
def process_message_with_ai(message_body: str) -> dict:
    """
    Processa a mensagem do usuário usando um LLM para extrair a intenção e os dados do agendamento.
    """
    
    # Instruções detalhadas para o modelo
    system_prompt = f"""
    Você é um assistente de IA para organização de agenda. Sua tarefa é analisar a mensagem do usuário e extrair as informações relevantes para um compromisso.
    
    Sua resposta DEVE ser APENAS um objeto JSON que se adere estritamente ao seguinte schema:
    {AgendamentoSchema.model_json_schema()}
    
    A data atual é: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.
    """

    try:
        response = client.chat.completions.create(
            model="gemini-2.5-flash", # Usando o modelo de melhor custo-benefício
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message_body}
            ],
            response_format={"type": "json_object"},
        )
        
        # O resultado é uma string JSON, que precisa ser parseada
        json_string = response.choices[0].message.content
        data = json.loads(json_string)
        
        # Validação Pydantic
        AgendamentoSchema(**data)
        
        return data

    except Exception as e:
        print(f"Erro ao processar mensagem com IA: {e}")
        # Retorna um erro padrão para que a aplicação possa responder
        return {
            "acao": "erro",
            "titulo": "Erro de Processamento",
            "data": datetime.now().strftime('%Y-%m-%d'),
            "hora": "09:00",
            "assunto_servico": "N/A",
            "duracao_minutos": 60,
            "recorrencia": "NONE",
            "id_compromisso": 0
        }

if __name__ == '__main__':
    # Teste da função de processamento
    test_message = "Quero agendar uma consulta com o Dr. Silva para a próxima terça-feira às 15h, vai durar 45 minutos."
    result = process_message_with_ai(test_message)
    print(json.dumps(result, indent=2))
    
    test_message_2 = "Cancela meu evento de Reunião com Cliente X de amanhã."
    result_2 = process_message_with_ai(test_message_2)
    print(json.dumps(result_2, indent=2))
