# IA de Agenda via WhatsApp com Sincronização Google Calendar

Este projeto implementa um assistente de agenda inteligente que interage com o usuário via WhatsApp e sincroniza os compromissos com o Google Calendar.

## Funcionalidades

| Funcionalidade | Descrição | Status |
| :--- | :--- | :--- |
| **Agendamento** | Criação de novos compromissos via mensagem de texto. | Implementado |
| **Reagendamento** | Alteração de data/hora de compromissos existentes. | Implementado |
| **Cancelamento/Exclusão** | Remoção de compromissos. | Implementado |
| **Consulta** | Consulta de compromissos para o dia atual. | Implementado |
| **NLP** | Processamento de Linguagem Natural para extrair intenção e dados. | Implementado |
| **Sincronização Google** | Sincronização bidirecional (CRUD) com o Google Calendar. | Implementado |
| **Recorrência** | Criação de eventos recorrentes. | **Pendente** (Complexidade da API do Google) |

## Arquitetura do Projeto

O projeto é construído em Python com o framework FastAPI, utilizando SQLite para o banco de dados local e a Meta Cloud API para a comunicação via WhatsApp.

| Arquivo | Descrição |
| :--- | :--- |
| `main.py` | Ponto de entrada da aplicação (FastAPI), rotas de webhook e lógica de agenda. |
| `database.py` | Módulo para gerenciar a conexão e operações CRUD com o banco de dados SQLite. |
| `whatsapp_api.py` | Módulo para gerenciar o envio de mensagens via Meta Cloud API. |
| `nlp_processor.py` | Módulo de IA para processamento de linguagem natural (NLP) e extração de dados. |
| `google_calendar_service.py` | Módulo para gerenciar o fluxo de autenticação OAuth 2.0 e operações CRUD no Google Calendar. |
| `.env` | Arquivo de configuração para variáveis de ambiente. |
| `requirements.txt` | Lista de dependências Python. |
| `credentials.json` | Arquivo de credenciais do Google Cloud (fornecido pelo usuário). |

## Guia de Implantação (Deploy)

O ambiente de desenvolvimento (sandbox) é temporário. Para colocar a aplicação em produção, siga os passos abaixo:

### 1. Configuração do Ambiente

1.  **Clone o Repositório:**
    ```bash
    git clone [URL_DO_SEU_REPOSITORIO]
    cd agenda_ia_whatsapp
    ```
2.  **Instale as Dependências:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configuração do Arquivo `.env`:**
    Crie o arquivo `.env` na raiz do projeto e preencha com suas credenciais:
    ```env
    # --- WhatsApp API (Meta Cloud API) ---
    WHATSAPP_ACCESS_TOKEN = "Vinicius_Leal_Token" # Seu token de acesso permanente
    WHATSAPP_PHONE_NUMBER_ID = "SEU_WHATSAPP_PHONE_NUMBER_ID" # ID do seu número de telefone
    WHATSAPP_VERIFY_TOKEN = "meu_token_real_123" # O token que você usou para verificar o webhook
    
    # --- Google Calendar API ---
    CREDENTIALS_FILE = "credentials.json"
    TOKEN_FILE = "token.json"
    ```
4.  **Credenciais do Google:**
    *   Coloque o arquivo `credentials.json` (o que você me forneceu) na raiz do projeto.

### 2. Configuração do Webhook do WhatsApp

1.  **Acesse o Painel de Desenvolvedor da Meta** e vá para a configuração do seu aplicativo WhatsApp Business.
2.  **URL de Callback:** Defina a URL de callback para `[SEU_DOMINIO]/webhook/whatsapp`.
3.  **Token de Verificação:** Use o valor de `WHATSAPP_VERIFY_TOKEN` (`meu_token_real_123`).
4.  **Assine os Campos:** Certifique-se de assinar o campo **`messages`**.

### 3. Autenticação com o Google Calendar (OAuth 2.0)

Este passo deve ser feito **após** o deploy da aplicação em seu domínio estável.

1.  **Acesse a URL de Início de Autenticação:**
    *   No seu navegador, acesse: `[SEU_DOMINIO]/auth/google/start`
2.  **Autorize o Acesso:**
    *   Siga as instruções na tela para fazer login na sua conta do Google e conceder as permissões à aplicação.
    *   O Google irá redirecioná-lo para a URL de callback, e o arquivo `token.json` será criado no seu servidor, armazenando as credenciais de acesso.

### 4. Execução da Aplicação

1.  **Inicie o Servidor:**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000
    ```
2.  **Exponha a Porta:**
    *   Se você estiver usando um serviço de hospedagem, certifique-se de que a porta 8000 (ou a porta que você escolher) esteja acessível publicamente e que o tráfego seja roteado para `[SEU_DOMINIO]`.

## Comandos de Uso via WhatsApp

O usuário pode interagir com a IA enviando mensagens de texto. A IA usará o NLP para interpretar a intenção.

| Ação | Exemplo de Mensagem |
| :--- | :--- |
| **Agendar** | "Quero agendar uma reunião com o cliente X amanhã às 10h, vai durar 1 hora." |
| **Consultar** | "Quais são meus compromissos para hoje?" |
| **Reagendar** | "Reagenda o compromisso ID 5 para a próxima sexta-feira às 14h." |
| **Cancelar/Excluir** | "Cancela o evento ID 8." |

## Próximos Passos (Melhorias)

1.  **Recorrência:** Implementar a lógica completa de recorrência (RRULE) para o Google Calendar.
2.  **Sincronização Bidirecional:** Implementar um mecanismo de webhook do Google Calendar para que alterações feitas diretamente no Google Agenda sejam refletidas no banco de dados local.
3.  **Validação de Data/Hora:** Adicionar validação para garantir que o usuário não agende compromissos em datas passadas ou em horários indisponíveis.

---
*Documentação gerada por **Manus AI***
