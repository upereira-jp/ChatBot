# database.py - Versão Final para PostgreSQL (SQLAlchemy)

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError

# 1. Configuração do Banco de Dados
# O Render injeta a URL de conexão no DATABASE_URL
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    # Esta é uma URL de fallback, mas o Render deve fornecer a correta
    raise ValueError("DATABASE_URL environment variable not set.")

# Cria o engine de conexão
engine = create_engine(DATABASE_URL)

# Base Declarativa para os modelos
Base = declarative_base()

# 2. Definição dos Modelos (Tabelas)

class Token(Base):
    """Modelo para armazenar o token de acesso do Google Calendar."""
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    token_json = Column(String)

class Compromisso(Base):
    """Modelo para armazenar os compromissos agendados via WhatsApp."""
    __tablename__ = "compromissos"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String)
    data_hora = Column(DateTime)
    assunto = Column(String)
    duracao = Column(Integer)  # Duração em minutos
    recorrencia = Column(String, nullable=True)
    # Adiciona um campo para rastrear o ID do evento no Google Calendar
    google_event_id = Column(String, nullable=True)

# 3. Inicialização do Banco de Dados
def initialize_db():
    """Cria as tabelas no banco de dados se elas não existirem."""
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully.")
    except SQLAlchemyError as e:
        print(f"Error creating database tables: {e}")

# 4. Criação da Sessão
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. Funções de CRUD para Compromissos
def get_compromisso_por_id(db, compromisso_id: int):
    """Retorna um compromisso pelo ID."""
    return db.query(Compromisso).filter(Compromisso.id == compromisso_id).first()

def get_db():
    """Função utilitária para obter uma sessão de banco de dados."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_compromisso(db, titulo: str, data_hora: datetime, assunto: str, duracao: int, recorrencia: str = None):
    """Cria um novo compromisso no banco de dados."""
    db_compromisso = Compromisso(
        titulo=titulo,
        data_hora=data_hora,
        assunto=assunto,
        duracao=duracao,
        recorrencia=recorrencia
    )
    db.add(db_compromisso)
    db.commit()
    db.refresh(db_compromisso)
    return db_compromisso

def get_compromissos_do_dia(db, data: datetime):
    """Retorna todos os compromissos para uma data específica."""
    start_of_day = data.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = data.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return db.query(Compromisso).filter(
        Compromisso.data_hora >= start_of_day,
        Compromisso.data_hora <= end_of_day
    ).order_by(Compromisso.data_hora).all()

def update_compromisso(db, compromisso_id: int, novos_dados: dict):
    """Atualiza um compromisso existente."""
    db_compromisso = db.query(Compromisso).filter(Compromisso.id == compromisso_id).first()
    if db_compromisso:
        for key, value in novos_dados.items():
            setattr(db_compromisso, key, value)
        db.commit()
        db.refresh(db_compromisso)
        return db_compromisso
    return None

def delete_compromisso(db, compromisso_id: int):
    """Deleta um compromisso pelo ID."""
    db_compromisso = db.query(Compromisso).filter(Compromisso.id == compromisso_id).first()
    if db_compromisso:
        db.delete(db_compromisso)
        db.commit()
        return True
    return False

# 6. Funções de CRUD para Token (Google Calendar)

def save_token(db, user_id: str, token_json: str):
    """Salva ou atualiza o token de acesso do Google Calendar."""
    db_token = db.query(Token).filter(Token.user_id == user_id).first()
    if db_token:
        db_token.token_json = token_json
    else:
        db_token = Token(user_id=user_id, token_json=token_json)
        db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token

def get_token(db, user_id: str):
    """Obtém o token de acesso do Google Calendar."""
    return db.query(Token).filter(Token.user_id == user_id).first()

def delete_token(db, user_id: str):
    """Deleta o token de acesso do Google Calendar."""
    db_token = db.query(Token).filter(Token.user_id == user_id).first()
    if db_token:
        db.delete(db_token)
        db.commit()
        return True
    return False

# 7. Chamada de Inicialização (para ser chamada no main.py)
# A função initialize_db() deve ser chamada uma vez na inicialização do FastAPI.
