from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.orm import Session
import json
from whatsapp_api import send_whatsapp_message  # Certifique-se de que o Twilio está sendo utilizado aqui!
from nlp_processor import process_message_with_ai, AgendaAction
from database import get_db, get_token, save_token, create_compromisso, get_compromissos_do_dia, update_compromisso, delete_compromisso, get_compromisso_por_id
from google_calendar_service import create_google_event, update_google_event, delete_google_event

# Inicializa a aplicação FastAPI
app = FastAPI()

# Rota para processar mensagens do WhatsApp
@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        print(f"LOG ENTRADA: {json.dumps(data)}")

        message_text = data.get("text")
        from_number = data.get("from")

        # 1. Processamento de IA
        ai_result: AgendaAction = process_message_with_ai(message_text)

        # 2. Lógica de Ação
        response_message = ""
        
        # Verifique se o token do Google Calendar está disponível
        token_record = get_token(db, user_id="main_user")  # Use o ID correto
        google_token = json.loads(token_record.token_json) if token_record else None

        # Verifica a ação que o usuário deseja realizar
        if ai_result.action == "agendar":
            # Lógica para agendar evento
            if not ai_result.data_hora:
                response_message = "Não consegui identificar a data e hora. Por favor, especifique melhor."
            else:
                # Cria compromisso no banco de dados local
                compromisso = create_compromisso(
                    db,
                    titulo=ai_result.titulo,
                    data_hora=ai_result.data_hora,
                    assunto=ai_result.assunto,
                    duracao=ai_result.duracao,
                    recorrencia=ai_result.recorrencia
                )
                response_message = f"Compromisso agendado com sucesso! ID Local: {compromisso.id}. Título: {compromisso.titulo} em {compromisso.data_hora.strftime('%d/%m/%Y %H:%M')}."
                
                # Cria o evento no Google Calendar
                if google_token:
                    event_id = create_google_event(google_token, compromisso)
                    if event_id:
                        # Atualiza o compromisso com o ID do Google
                        update_compromisso(db, compromisso.id, {"google_event_id": event_id})
                        response_message += f" Sincronizado com o Google Calendar."

        elif ai_result.action == "reagendar":
            # Lógica para reagendar evento
            if not ai_result.id_compromisso or not ai_result.data_hora:
                response_message = "Para reagendar, preciso do ID do compromisso e da nova data/hora."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    # Atualiza o compromisso no banco de dados
                    update_compromisso(db, compromisso.id, {"data_hora": ai_result.data_hora})
                    response_message = f"Compromisso ID {compromisso.id} reagendado para {ai_result.data_hora.strftime('%d/%m/%Y %H:%M')}."
                    
                    # Atualiza o evento no Google Calendar
                    if google_token and compromisso.google_event_id:
                        update_google_event(google_token, compromisso)
                        response_message += " Sincronizado com o Google Calendar."
                else:
                    response_message = f"Compromisso com ID {ai_result.id_compromisso} não encontrado."

        elif ai_result.action == "cancelar":
            # Lógica para cancelar evento
            if not ai_result.id_compromisso:
                response_message = "Para cancelar, preciso do ID do compromisso."
            else:
                compromisso = get_compromisso_por_id(db, ai_result.id_compromisso)
                if compromisso:
                    # Deleta o compromisso no banco de dados
                    delete_compromisso(db, compromisso.id)
                    response_message = f"Compromisso ID {compromisso.id} cancelado com sucesso."
                    
                    # Deleta o evento no Google Calendar
                    if google_token and compromisso.google_event_id:
                        delete_google_event(google_token, compromisso.google_event_id)
                        response_message += " Sincronizado com o Google Calendar."
                else:
                    response_message = f"Compromisso com ID {ai_result.id_compromisso} não encontrado."

        elif ai_result.action == "consultar":
            # Lógica para consultar compromissos
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

        # Envia a resposta de volta via WhatsApp
        send_whatsapp_message(from_number, response_message)
        
        return {"status": "ok", "message": "Mensagem processada."}


@app.get("/")
def read_root():
    return {"message": "Servidor está funcionando!"}


    except Exception as e:
        # Caso haja algum erro
        print(f"Erro no processamento da mensagem: {e}")
        send_whatsapp_message(from_number, "Ocorreu um erro interno ao processar sua solicitação.")
        raise HTTPException(status_code=500, detail=str(e))
