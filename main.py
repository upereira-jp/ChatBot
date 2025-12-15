# main.py — versão limpa (U+00A0 removido, indentação normalizada)

from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session
import json
import traceback
from datetime import datetime

# --- IMPORTAÇÕES LOCAIS ---
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
    get_compromisso_por_id,
)
from google_calendar_service import (
    create_google_event,
    update_google_event,
    delete_google_event,
    google_auth_flow_start,
    google_auth_flow_callback,
)

# Inicializa a aplicação FastAPI
app = FastAPI()

# ID fixo do usuário principal
MAIN_USER_ID = "main_user"

# Token de verificação do Meta (ideal usar variável de ambiente em produção)
VERIFY_TOKEN = "seu_token_secreto_e_forte_aqui_12345"


# ==================================
# PROCESSAMENTO EM SEGUNDO PLANO
# ==================================

def process_message_background(data: dict, db: Session) -> None:
    """
    Processa a lógica pesada (IA, DB, Google Calendar, WhatsApp)
    em background para responder rapidamente ao Meta.
    """
    try:
        print(f"LOG PAYLOAD (Background): {json.dumps(data)}", flush=True)

        # Verifica se é uma mensagem de usuário
        if not (
            data.get("entry")
            and data["entry"][0].get("changes")
            and data["entry"][0]["changes"][0].get("value")
            and data["entry"][0]["changes"][0]["value"].get("messages")
        ):
            print(
                "LOG (Background): Payload não contém mensagem de usuário.",
                flush=True,
            )
            return

        message_data = data["entry"][0]["changes"][0]["value"]["messages"][0]
        message_text = message_data["text"]["body"]
        from_number = message_data["from"]

        ai_result: AgendaAction = process_message_with_ai(message_text)
        response_message = ""

        token_record = get_token(db, user_id=MAIN_USER_ID)
        google_token = json.loads(token_record.token_json) if token_record else None

        # ------------------------------
        # AGENDAR
        # ------------------------------
        if ai_result.action == "agendar":
            if not ai_result.data_hora:
                response_message = (
                    "Não consegui identificar a data e hora. Especifique melhor."
                )
            else:
                compromisso = create_compromisso(
                    db,
                    titulo=ai_result.titulo,
                    data_hora=ai_result.data_hora,
                    assunto=ai_result.assunto,
                    duracao=ai_result.duracao,
                    recorrencia=ai_result.recorrencia,
                )

                response_message = (
                    f"Compromisso agendado! ID {compromisso.id}. "
                    f"{compromisso.titulo} em "
                    f"{compromisso.data_hora.strftime('%d/%m/%Y %H:%M')}"
                )

                if google_token:
                    event_id = create_google_event(google_token, compromisso)
                    if event_id:
                        update_compromisso(
                            db,
                            compromisso.id,
                            {"google_event_id": event_id},
                        )
                        response_message += " (Google Calendar OK)"
                else:
                    response_message += (
                        "\n⚠ Google Calendar não autorizado. "
                        "Acesse /auth/google/start"
                    )

        # ------------------------------
        # REAGENDAR
        # ------------------------------
        elif ai_result.action == "reagendar":
            if not ai_result.id_compromisso or not ai_result.data_hora:
                response_message = "Informe o ID e a nova data/hora."
            else:
                compromisso = get_compromisso_por_id(
                    db, ai_result.id_compromisso
                )
                if compromisso:
                    update_compromisso(
                        db,
                        compromisso.id,
                        {"data_hora": ai_result.data_hora},
                    )
                    response_message = (
                        f"Compromisso {compromisso.id} reagendado para "
                        f"{ai_result.data_hora.strftime('%d/%m/%Y %H:%M')}"
                    )

                    if google_token and compromisso.google_event_id:
                        update_google_event(google_token, compromisso)
                        response_message += " (Google Calendar OK)"
                else:
                    response_message = "Compromisso não encontrado."

        # ------------------------------
        # CANCELAR
        # ------------------------------
        elif ai_result.action == "cancelar":
            if not ai_result.id_compromisso:
                response_message = "Informe o ID do compromisso."
            else:
                compromisso = get_compromisso_por_id(
                    db, ai_result.id_compromisso
                )
                if compromisso:
                    delete_compromisso(db, compromisso.id)
                    response_message = (
                        f"Compromisso {compromisso.id} cancelado."
                    )

                    if google_token and compromisso.google_event_id:
                        delete_google_event(
                            google_token, compromisso.google_event_id
                        )
                        response_message += " (Google Calendar OK)"
                else:
                    response_message = "Compromisso não encontrado."

        # ------------------------------
        # CONSULTAR
        # ------------------------------
        elif ai_result.action == "consultar":
            data_consulta = (
                ai_result.data_hora.date()
                if ai_result.data_hora
                else datetime.now().date()
            )

            compromissos = get_compromissos_do_dia(
                db, datetime.combine(data_consulta, datetime.min.time())
            )

            if compromissos:
                lista = "\n".join(
                    f"ID {c.id}: {c.titulo} ({c.assunto}) às "
                    f"{c.data_hora.strftime('%H:%M')}"
                    for c in compromissos
                )
                response_message = (
                    f"Compromissos para {data_consulta.strftime('%d/%m/%Y')}:\n"
                    f"{lista}"
                )
            else:
                response_message = (
                    f"Nenhum compromisso para {data_consulta.strftime('%d/%m/%Y')}"
                )

        else:
            response_message = (
                "Não entendi. Ex.: 'Agendar reunião amanhã às 10h'."
            )

        send_whatsapp_message(from_number, response_message)

    except Exception as e:
        try:
            from_number = (
                data["entry"][0]["changes"][0]["value"]["messages"][0][
                    "from"
                ]
            )
            send_whatsapp_message(
                from_number, "Ocorreu um erro interno ao processar sua solicitação."
            )
        except Exception:
            pass

        print(
            f"Erro no processamento (Background): {e}\n"
            f"{traceback.format_exc()}",
            flush=True,
        )


# ==================================
# ROTAS GOOGLE CALENDAR
# ==================================

@app.get("/auth/google/start")
async def google_auth_start():
    try:
        auth_url = google_auth_flow_start()
        return RedirectResponse(auth_url)
    except Exception as e:
        print(f"Erro ao iniciar Google Auth: {e}", flush=True)
        return HTMLResponse(
            content=f"<h1>Erro no Google Auth</h1><p>{e}</p>", status_code=500
        )


@app.get("/auth/google/callback")
async def google_auth_callback(
    request: Request, db: Session = Depends(get_db)
):
    try:
        full_url = str(request.url)
        token_info = google_auth_flow_callback(full_url)
        save_token(db, user_id=MAIN_USER_ID, token_json=json.dumps(token_info))

        return HTMLResponse(
            content=(
                "<h1>✅ Autenticação Concluída!</h1>"
                "<p>Google Calendar sincronizado.</p>"
            ),
            status_code=200,
        )
    except Exception as e:
        print(f"Erro no callback do Google: {e}", flush=True)
        return HTMLResponse(
            content=f"<h1>❌ Erro na Autenticação</h1><p>{e}</p>",
            status_code=500,
        )


# ==================================
# ROTAS DA APLICAÇÃO
# ==================================

@app.get("/")
def read_root():
    return {"message": "Servidor está funcionando!"}


@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print(
                f"Webhook verificado. Challenge: {challenge}", flush=True
            )
            return PlainTextResponse(
                content=str(challenge), status_code=200
            )
        raise HTTPException(
            status_code=403, detail="Token de verificação incorreto"
        )

    raise HTTPException(
        status_code=400,
        detail="Parâmetros ausentes (rota usada pelo Meta).",
    )


@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    print("POST recebido em /webhook/whatsapp", flush=True)
    try:
        data = await request.json()
        background_tasks.add_task(process_message_background, data, db)
        return {"status": "ok", "message": "Evento agendado."}
    except Exception as e:
        print(
            f"Erro fatal no POST: {e}\n{traceback.format_exc()}",
            flush=True,
        )
        raise HTTPException(
            status_code=500, detail="Erro ao processar payload"
        )
