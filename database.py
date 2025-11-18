import sqlite_utils
from datetime import datetime, timedelta
import json

DB_PATH = "agenda.db"
DB = sqlite_utils.Database(DB_PATH)

def initialize_db():
    """
    Inicializa o banco de dados e cria a tabela 'compromissos' se ela não existir.
    """
    if "compromissos" not in DB.table_names():
        DB["compromissos"].create(
            {
                "id": int,
                "whatsapp_id": str, # ID do usuário do WhatsApp
                "titulo": str,
                "data_hora_inicio": datetime,
                "data_hora_fim": datetime,
                "assunto_servico": str,
                "duracao_minutos": int,
                "recorrencia": str, # Armazenar regras de recorrência (ex: 'DAILY', 'WEEKLY')
                "data_criacao": datetime,
                "status": str # 'agendado', 'cancelado', 'concluido'
            },
            pk="id"
        )
        # Criar índice para consultas rápidas por usuário e data
        DB["compromissos"].create_index(["whatsapp_id", "data_hora_inicio"])
        print(f"Tabela 'compromissos' criada em {DB_PATH}")

def save_compromisso(whatsapp_id: str, titulo: str, data_hora_inicio: datetime, duracao_minutos: int, assunto_servico: str, recorrencia: str = None):
    """
    Salva um novo compromisso no banco de dados.
    """
    data_hora_fim = data_hora_inicio + timedelta(minutes=duracao_minutos)
    
    compromisso = {
        "whatsapp_id": whatsapp_id,
        "titulo": titulo,
        "data_hora_inicio": data_hora_inicio.isoformat(),
        "data_hora_fim": data_hora_fim.isoformat(),
        "assunto_servico": assunto_servico,
        "duracao_minutos": duracao_minutos,
        "recorrencia": recorrencia,
        "data_criacao": datetime.now().isoformat(),
        "status": "agendado"
    }
    
    DB["compromissos"].insert(compromisso, alter=True)
    return compromisso

def get_compromissos_by_day(whatsapp_id: str, date: datetime.date):
    """
    Busca compromissos agendados para um dia específico.
    """
    start_of_day = datetime.combine(date, datetime.min.time()).isoformat()
    end_of_day = datetime.combine(date, datetime.max.time()).isoformat()
    
    results = DB.query(
        """
        SELECT * FROM compromissos
        WHERE whatsapp_id = ?
        AND data_hora_inicio >= ?
        AND data_hora_inicio <= ?
        AND status = 'agendado'
        ORDER BY data_hora_inicio
        """,
        [whatsapp_id, start_of_day, end_of_day]
    )
    return list(results)

def update_compromisso(id_compromisso: int, **kwargs):
    """
    Atualiza um compromisso existente.
    """
    DB["compromissos"].update(id_compromisso, kwargs)
    return DB["compromissos"].get(id_compromisso)

def delete_compromisso(id_compromisso: int):
    """
    Exclui um compromisso existente.
    """
    DB["compromissos"].delete(id_compromisso)
    return True

def get_compromisso_by_id(id_compromisso: int):
    """
    Busca um compromisso pelo ID.
    """
    try:
        return DB["compromissos"].get(id_compromisso)
    except sqlite_utils.db.NotFoundError:
        return None

def get_compromissos_by_whatsapp_id(whatsapp_id: str):
    """
    Busca todos os compromissos de um usuário.
    """
    results = DB.query(
        """
        SELECT * FROM compromissos
        WHERE whatsapp_id = ?
        AND status = 'agendado'
        ORDER BY data_hora_inicio
        """,
        [whatsapp_id]
    )
    return list(results)

# Funções de update, delete e recorrência serão adicionadas conforme a Fase 6.

if __name__ == '__main__':
    # Teste de inicialização e inserção
    initialize_db()
    
    # Exemplo de uso
    from datetime import timedelta
    
    # Limpar a tabela para o teste
    DB["compromissos"].delete_where("1")
    
    # Criar um compromisso de teste
    data_teste = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    save_compromisso(
        whatsapp_id="5511999999999",
        titulo="Reunião com Cliente X",
        data_hora_inicio=data_teste,
        duracao_minutos=60,
        assunto_servico="Apresentação de Proposta"
    )
    
    # Consultar compromissos
    compromissos_amanha = get_compromissos_by_day(
        whatsapp_id="5511999999999",
        date=data_teste.date()
    )
    
    print("\nCompromissos para amanhã:")
    print(json.dumps(compromissos_amanha, indent=2))
    
    # Verificar se o compromisso foi salvo
    assert len(compromissos_amanha) == 1
    print("\nTeste de banco de dados concluído com sucesso!")
