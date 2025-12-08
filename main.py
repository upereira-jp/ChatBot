# main.py - Versão Final Corrigida para Render (PostgreSQL/SQLAlchemy)

import os
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException
from starlette.responses import Response
from sqlalchemy.orm import Session

# Importações Corrigidas (Absolutas e Nomes Corretos)
from database import (
    initialize_db,
    get_db,
    create_compromisso,
    get_compromissos_do_dia,
    update_compromisso,
    delete_compromisso,
    get_compromisso_por_id, # Função adicionada ao database.py na última correção
    get_token,
    save_token,
)
from whatsapp_api import send_whatsapp_message
from nlp_processor import process_message_with_ai, AgendaAction
from google_calendar_service import start_auth_flow, handle_auth_callback, create_google_event, update_google_event, delete_google_event

# --- Configuração ---
# O Render injeta as variáveis de ambiente
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
# O user_id será usado para buscar o token do Google Calendar no DB
MAIN_USER_ID = "main_user" 

app = FastAPI()

# --- Eventos de Inicialização ---

@app.on_event("startup")
def on_startup():
    """Inicializa o banco de dados na inicialização do servidor."""
    initialize_db()

# --- Rotas de Autenticação Google Calendar ---

@app.get("/auth/google/start")
def start_auth_flow_route():
    """Inicia o fluxo de autenticação OAuth 2.0."""
    return start_auth_flow()

@app.get("/auth/google/callback")
def handle_auth_callback_route(code: str, db: Session = Depends(get_db)):
    """Lida com o retorno de chamada do Google e salva o token."""
    try:
        token_json = handle_auth_callback(code)
        # Salva o token no banco de dados
        save_token(db, user_id=MAIN_USER_ID, token_json=token_json)
        return {"message": "Autenticação Google Calendar concluída com sucesso! O token foi salvo."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na autenticação: {e}")

# --- Rota do Webhook do WhatsApp ---

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    """Verifica o webhook do WhatsApp (GET request)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode and token:
        # ATENÇÃO: Substitua VERIFY_TOKEN pela forma como você carrega o token (ex: os.getenv("WHATSAPP_VERIFY_TOKEN"))
        # Se VERIFY_TOKEN for uma variável global, mantenha-a.
        if mode == "subscribe" and token == VERIFY_TOKEN:
            # CORREÇÃO: Retorna o desafio como texto simples (text/plain)
            return Response(content=challenge, media_type="text/plain")
        else:
            raise HTTPException(status_code=403, detail="Token de verificação inválido.")
    raise HTTPException(status_code=400, detail="Parâmetros ausentes.")

@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(request: Request, db: Session = Depends(get_db)):
    """Processa as mensagens recebidas do WhatsApp (POST request)."""
    try:
        data = await request.json()

        print(f"DEBUG: Recebido POST da Meta: {json.dumps(data)}")
        
        # Lógica para extrair a mensagem de texto (simplificada)
        message_text = ""
        # ... (Sua lógica de extração de mensagem aqui) ...
        
        # Simulação de extração de mensagem para teste
        # Você deve implementar a lógica real de extração de 'data'
        
        # Apenas para fins de teste, vamos assumir que a mensagem está em 'data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]'
        try:
            message_text = data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
            from_number = data["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
        except (KeyError, IndexError):
            # Ignora notificações de status, etc.
            return {"status": "ok", "message": "Ignorando notificação de status."}

        # 1. Processamento de IA
        ai_result: AgendaAction = process_message_with_ai(message_text)
        
        # 2. Lógica de Ação
        response_message = ""
        
        # Tenta obter o token do Google Calendar
        token_record = get_token(db, user_id=MAIN_USER_ID)
        google_token = json.loads(token_record.token_json) if token_record else None

        if ai_result.action == "agendar":
            # Lógica de Agendamento
            if not ai_result.data_hora:
                response_message = "Não consegui identificar a data e hora. Por favor, especifique melhor."
            else:
                # Cria no DB local
                compromisso = create_compromisso(
                    db,
                    titulo=ai_result.titulo,
                    data_hora=ai_result.data_hora,
                    assunto=ai_result.assunto,
                    duracao=ai_result.duracao,
                    recorrencia=ai_result.recorrencia
                )
                response_message = f"Compromisso agendado com sucesso! ID Local: {compromisso.id}. Título: {compromisso.titulo} em {compromisso.data_hora.strftime('%d/%m/%Y %H:%M')}."
                
                # Cria no Google Calendar
                if google_token:
                    event_id = create_google_event(google_token, compromisso)
                    if event_id:
                        # Atualiza o compromisso local com o ID do Google
                        update_compromisso(db, compromisso.id, {"google_event_id": event_id})
                        response_message += f" Sincronizado com o Google Calendar."

        elif ai_result.action == "reagendar":
            # Lógica de Reagendamento
            if not ai_result.id_compromisso or not ai_result.data_hora:
                response_message = "Para reagendar, preciso do ID do compromisso e da nova data/hora."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    # Atualiza no DB local
                    update_compromisso(db, compromisso.id, {"data_hora": ai_result.data_hora})
                    response_message = f"Compromisso ID {compromisso.id} reagendado para {ai_result.data_hora.strftime('%d/%m/%Y %H:%M')}."
                    
                    # Atualiza no Google Calendar
                    if google_token and compromisso.google_event_id:
                        update_google_event(google_token, compromisso)
                        response_message += " Sincronizado com o Google Calendar."
                else:
                    response_message = f"Compromisso com ID {ai_result.id_compromisso} não encontrado."

        elif ai_result.action == "cancelar":
            # Lógica de Cancelamento/Exclusão
            if not ai_result.id_compromisso:
                response_message = "Para cancelar, preciso do ID do compromisso."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    # Deleta no DB local
                    delete_compromisso(db, compromisso.id)
                    response_message = f"Compromisso ID {compromisso.id} cancelado com sucesso."
                    
                    # Deleta no Google Calendar
                    if google_token and compromisso.google_event_id:
                        delete_google_event(google_token, compromisso.google_event_id)
                        response_message += " Sincronizado com o Google Calendar."
                else:
                    response_message = f"Compromisso com ID {ai_result.id_compromisso} não encontrado."

        elif ai_result.action == "consultar":
            # Lógica de Consulta
            data_consulta = ai_result.data_hora.date() if ai_result.data_hora else datetime.now().date()
            
            compromissos = get_compromissos_do_dia(db, datetime.combine(data_consulta, datetime.min.time()))
            
            if compromissos:
                lista = "\n".join([
                    f"ID {c.id}: {c.titulo} ({c.assunto}) às {c.data_hora.strftime('%H:%M')}"
                    for c in compromissos
                ])
                response_message = f"Compromissos para {data_consulta.strftime('%d/%m/%Y')}:\n{lista}"
            else:
                response_message = f"Nenhum compromisso encontrado para {data_consulta.strftime('%d/%m/%Y')}."

        else:
            response_message = "Desculpe, não entendi a sua solicitação. Tente algo como: 'Agendar reunião amanhã às 10h' ou 'Consultar agenda de hoje'."

        # 3. Envio da Resposta (Descomente após o deploy e configuração do WHATSAPP_PHONE_NUMBER_ID)
        # send_whatsapp_message(from_number, response_message)
        
        return {"status": "ok", "message": "Mensagem processada."}

    except Exception as e:
        # Em caso de erro, você pode querer logar ou enviar uma mensagem de erro
        print(f"Erro no processamento da mensagem: {e}")
        # send_whatsapp_message(from_number, "Ocorreu um erro interno ao processar sua solicitação.")
        raise HTTPException(status_code=500, detail=str(e))

# --- Rota de Teste (Opcional) ---

@app.get("/")
def read_root():
    return {"Hello": "IA de Agenda via WhatsApp está rodando!"}
