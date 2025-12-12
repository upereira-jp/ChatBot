# main.py corrigido (indentação, remoção de U+00A0, blocos arrumados)

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
import json
from datetime import datetime, time, date
from whatsapp_api import send_whatsapp_message
from nlp_processor import process_message_with_ai, AgendaAction
from database import (
    get_db,
    get_token,
    save_token,
    create_compromisso,
    get_compromissos_do_dia,
    update_compromisso,
    delete_compromisso,
    get_compromisso_por_id
)
from google_calendar_service import (
    create_google_event,
    update_google_event,
    delete_google_event,
    google_auth_flow_start,
    google_auth_flow_callback
)
import traceback

app = FastAPI()

MAIN_USER_ID = "main_user"
VERIFY_TOKEN = "meu_token_real_123"


# =====================
#  AUTENTICAÇÃO GOOGLE
# =====================

@app.get("/auth/google/start")
async def google_auth_start():
    try:
        auth_url = google_auth_flow_start()
        return RedirectResponse(auth_url)
    except Exception as e:
        print(f"Erro ao iniciar o fluxo de autenticação: {e}")
        return HTMLResponse(
            content=f"<h1>Erro ao iniciar o Google Auth</h1><p>Detalhe: {e}</p>",
            status_code=500
        )


@app.get("/auth/google/callback")
async def google_auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        full_url = str(request.url)
        token_info = google_auth_flow_callback(full_url)
        save_token(db, user_id=MAIN_USER_ID, token_json=json.dumps(token_info))

        return HTMLResponse(
            content="<h1>✅ Autenticação Concluída!</h1><p>Google Calendar sincronizado.</p>",
            status_code=200
        )

    except Exception as e:
        print(f"Erro no callback do Google: {e}")
        return HTMLResponse(
            content=f"<h1>❌ Erro na Autenticação</h1><p>{e}</p>",
            status_code=500
        )


# ============================
#  ROTA DE STATUS DO SERVIDOR
# ============================

@app.get("/")
def read_root():
    return {"message": "Servidor está funcionando!"}


# ==========================
#  WEBHOOK GET - VERIFICAÇÃO
# ==========================

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("--- VERIFICAÇÃO DE WEBHOOK (GET) OK ---")
            return HTMLResponse(content=challenge, status_code=200)
        else:
            print("--- FALHA NA VERIFICAÇÃO (GET) ---")
            raise HTTPException(status_code=403, detail="Token incorreto")

    print("--- GET SEM PARÂMETROS DE VERIFICAÇÃO ---")
    raise HTTPException(status_code=400, detail="Parâmetros ausentes")


# ================================
#  WEBHOOK POST - MENSAGENS WHATSAPP
# ================================

@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(request: Request, db: Session = Depends(get_db)):
    print("--- POST RECEBIDO EM /webhook/whatsapp ---")

    try:
        data = await request.json()
        print(f"LOG PAYLOAD: {json.dumps(data)}")

        # Verificação do formato do payload
        if not (
            data.get('entry') and
            data['entry'][0].get('changes') and
            data['entry'][0]['changes'][0].get('value') and
            data['entry'][0]['changes'][0]['value'].get('messages')
        ):
            print("LOG: Não é mensagem de usuário.")
            return {"status": "ok", "message": "Evento ignorado."}

        message_data = data['entry'][0]['changes'][0]['value']['messages'][0]
        message_text = message_data['text']['body']
        from_number = message_data['from']

        ai_result: AgendaAction = process_message_with_ai(message_text)
        response_message = ""

        token_record = get_token(db, user_id=MAIN_USER_ID)
        google_token = json.loads(token_record.token_json) if token_record else None

        # ==============================
        # AÇÃO: AGENDAR
        # ==============================
        if ai_result.action == "agendar":
            if not ai_result.data_hora:
                response_message = "Não consegui identificar a data e hora."
            else:
                compromisso = create_compromisso(
                    db,
                    titulo=ai_result.titulo,
                    data_hora=ai_result.data_hora,
                    assunto=ai_result.assunto,
                    duracao=ai_result.duracao,
                    recorrencia=ai_result.recorrencia
                )
                response_message = (
                    f"Compromisso criado! ID {compromisso.id}. "
                    f"{compromisso.titulo} — {compromisso.data_hora.strftime('%d/%m/%Y %H:%M')}"
                )

                if google_token:
                    event_id = create_google_event(google_token, compromisso)
                    if event_id:
                        update_compromisso(db, compromisso.id, {"google_event_id": event_id})
                        response_message += " (Google Calendar OK)"
                else:
                    response_message += "\n⚠ Google Calendar não autorizado. Acesse /auth/google/start"

        # ==============================
        # AÇÃO: REAGENDAR
        # ==============================
        elif ai_result.action == "reagendar":
            if not ai_result.id_compromisso or not ai_result.data_hora:
                response_message = "Preciso do ID e da nova data/hora."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    update_compromisso(db, compromisso.id, {"data_hora": ai_result.data_hora})
                    response_message = (
                        f"Compromisso {compromisso.id} reagendado para "
                        f"{ai_result.data_hora.strftime('%d/%m/%Y %H:%M')}"
                    )

                    if google_token and compromisso.google_event_id:
                        update_google_event(google_token, compromisso)
                        response_message += " (Google Calendar OK)"
                else:
                    response_message = "Compromisso não encontrado."

        # ==============================
        # AÇÃO: CANCELAR
        # ==============================
        elif ai_result.action == "cancelar":
            if not ai_result.id_compromisso:
                response_message = "Preciso do ID do compromisso para cancelar."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    delete_compromisso(db, compromisso.id)
                    response_message = f"Compromisso {compromisso.id} cancelado."

                    if google_token and compromisso.google_event_id:
                        delete_google_event(google_token, compromisso.google_event_id)
                        response_message += " (Google Calendar OK)"
                else:
                    response_message = "Compromisso não encontrado."

        # ==============================
        # AÇÃO: CONSULTAR
        # ==============================
        elif ai_result.action == "consultar":
            data_consulta = (
                ai_result.data_hora.date() if ai_result.data_hora else datetime.now().date()
            )

            compromissos = get_compromissos_do_dia(
                db,
                datetime.combine(data_consulta, datetime.min.time())
            )

            if compromissos:
                lista = "\n".join([
                    f"ID {c.id}: {c.titulo} ({c.assunto}) — {c.data_hora.strftime('%H:%M')}"
                    for c in compromissos
                ])
                response_message = f"Compromissos de {data_consulta.strftime('%d/%m/%Y')}:\n{lista}"
            else:
                response_message = f"Nenhum compromisso para {data_consulta.strftime('%d/%m/%Y')}"

        else:
            response_message = (
                "Desculpe, não entendi. Tente: 'Agendar reunião amanhã às 10h'."
            )

        send_whatsapp_message(from_number, response_message)
        return {"status": "ok"}

    except Exception as e:
        print(f"Erro no processamento: {e}\n{traceback.format_exc()}")

        # tentativa de enviar msg de erro ao usuário
        try:
            from_number = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
            send_whatsapp_message(from_number, "Ocorreu um erro interno.")
        except:
            pass

        raise HTTPException(status_code=500, detail=str(e))
