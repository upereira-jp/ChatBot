# nlp_processor.py - Versão Final Corrigida

import os
import json
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from openai import OpenAI

# O cliente OpenAI é inicializado automaticamente com a variável de ambiente OPENAI_API_KEY
client = OpenAI()

# 1. Definição da Classe que o main.py precisa importar
class AgendaAction(BaseModel):
    """Estrutura de dados para a ação e os parâmetros extraídos pela IA."""
    action: str  # Ex: agendar, reagendar, cancelar, consultar
    titulo: Optional[str] = None
    data_hora: Optional[datetime] = None
    assunto: Optional[str] = None
    duracao: Optional[int] = 120  # Duração padrão em minutos
    recorrencia: Optional[str] = None
    id_compromisso: Optional[int] = None  # Para reagendar/cancelar

# 2. Função de Processamento de IA
def process_message_with_ai(message: str) -> AgendaAction:
    """Envia a mensagem para a OpenAI para extrair a ação e os parâmetros."""
    
    # O prompt deve ser o mais claro possível para garantir o formato JSON
    prompt = f"""
    Você é um assistente de agendamento de compromissos. Sua tarefa é analisar a mensagem do usuário e extrair a intenção (action) e os parâmetros relevantes em formato JSON.

    Regras de Extração:
    1. A 'action' deve ser uma das seguintes: 'agendar', 'reagendar', 'cancelar', 'consultar'.
    2. A 'data_hora' deve ser convertida para o formato ISO 8601 (YYYY-MM-DDTHH:MM:SS) e deve ser no futuro. Se a data não for especificada, use a data de hoje. Se a hora não for especificada, use 09:00.
    3. O 'id_compromisso' é obrigatório para 'reagendar' e 'cancelar'.
    4. O 'duracao' é em minutos. Use 120 (2 horas) como padrão se não for especificado.
    5. O JSON de saída deve ser estritamente compatível com o schema AgendaAction.

    Mensagem do Usuário: "{message}"
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # Modelo rápido para extração de dados
            messages=[
                {"role": "system", "content": "Você é um assistente de agendamento que retorna estritamente um objeto JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        # O modelo retorna uma string JSON
        json_string = response.choices[0].message.content
        
        # Converte a string JSON para o objeto AgendaAction
        data = json.loads(json_string)
        
        # Valida e retorna o objeto Pydantic
        return AgendaAction(**data)

    except Exception as e:
        # Em caso de falha na IA ou no parsing, retorna uma ação padrão de erro
        print(f"Erro na chamada da OpenAI: {e}")
        return AgendaAction(action="erro", titulo=f"Erro de IA: {e}")

# --- Fim do nlp_processor.py ---
