# Engineering AI Assistant — LLM Chatbot with Multi-Turn Memory

A Flask chatbot backed by the OpenAI API. It remembers earlier messages in a conversation, limits how much history it sends to the model (context-window management), and has a simple responsive web UI.

## 1. Project overview

The browser UI sends each message to a Flask backend (`POST /api/chat`). The backend stores the conversation in memory, builds a request made of the **system prompt + recent history + new message**, calls the OpenAI API, and returns the reply. The API key lives only on the server.

## 2. Objectives

- Use a real LLM API end to end (no canned replies).
- Keep multi-turn memory per conversation, with isolated conversations.
- Control context size with configurable message truncation.
- Handle errors gracefully and keep secrets out of the frontend and Git.

## 3. Features

- Chat UI with distinct user/assistant bubbles, loading indicator, auto-scroll, error banner, welcome message
- Enter to send (Shift+Enter = new line), duplicate-submit protection
- **New Chat** (fresh conversation ID) and **Clear** (erase current conversation)
- Configurable history limit and model via `.env`
- Safe rendering (`textContent`, never `innerHTML`)
- JSON error responses with proper HTTP status codes
- Mock-based pytest suite + optional real-API integration test

## 4. Technology stack

Python, Flask, OpenAI Python SDK (`openai`), python-dotenv, HTML5, CSS3, JavaScript (Fetch API), pytest, Git/GitHub.

## 5. System architecture

```
Browser (index.html + script.js)
   │  fetch POST /api/chat {conversation_id, message}
   ▼
app.py (Flask routes, validation, error → JSON)
   ├── services/conversation_manager.py   memory + truncation (no API code)
   └── services/llm_service.py            system prompt + OpenAI call + error mapping
                                              │
                                              ▼
                                         OpenAI API
```

Request flow for `/api/chat`:

1. Validate JSON, `conversation_id`, and `message`.
2. `build_context()` → `[system prompt] + [newest N stored messages] + [new user message]`.
3. `LLMService.generate_reply()` calls OpenAI.
4. Only on success, the user message and reply are saved as one turn.
5. Return `{conversation_id, reply, history_messages}`.

## 6. Project directory structure

```
llm-chatbot/
├── app.py
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
├── README.md
├── services/
│   ├── __init__.py
│   ├── llm_service.py
│   └── conversation_manager.py
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   └── js/script.js
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_chat_api.py
    ├── test_conversation_manager.py
    ├── test_llm_service.py
    └── test_integration_real_api.py
```

## 7. Installation (Windows PowerShell)

Requires Python 3.9+ (check with `python --version`).

```powershell
cd llm-chatbot

# Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

(In Command Prompt use `venv\Scripts\activate.bat` instead.)

```powershell
# Install dependencies
pip install -r requirements.txt
```

## 8. OpenAI API key and environment variables

1. Create an account at <https://platform.openai.com> and open the **API keys** page to create a key. API usage is billed; **do not assume free credits exist** — check your account's billing/usage page.
2. Pick a chat-capable model available to your account from OpenAI's model list.
3. Create your local config file:

```powershell
Copy-Item .env.example .env
notepad .env
```

4. Fill in the values:

| Variable | Meaning |
|---|---|
| `OPENAI_API_KEY` | Your secret key (never share or commit it) |
| `OPENAI_MODEL` | Model name to use; change it any time without editing code |
| `MAX_HISTORY_MESSAGES` | How many previous messages to send (default 10, minimum 2) |
| `OPENAI_TIMEOUT_SECONDS` | Optional request timeout (default 30) |

If the key or model is missing, the app still starts but chat requests return a clear "server is not configured" error.

## 9. Start the app

```powershell
python app.py
start http://127.0.0.1:5000
```

## 10. Using the chatbot

Type a question and press **Enter** (Shift+Enter adds a new line). **New Chat** starts a separate conversation with empty memory; **Clear** wipes the current conversation.

## 11. Multi-turn memory

Each conversation has a unique ID (`conv_<random hex>`) created by `POST /api/conversations`. Messages are stored as `{"role": "user"|"assistant", "content": ...}` in order in a Python dictionary keyed by that ID, so conversations cannot see each other. Every request re-sends the recent history, which is how the model can recall your name or topic from earlier turns (LLM APIs are stateless).

**Storage limitation:** the dictionary is in RAM only. Conversations are lost on server restart, and it does not work across multiple server processes. All access goes through `ConversationManager`, so SQLite/Redis can replace it later without changing `app.py`.

## 12. Context window management

`MAX_HISTORY_MESSAGES` limits how many **previous** messages are sent. The request is always: system prompt + newest N stored messages + the new user message.

- The system prompt is added separately, so truncation can never remove it.
- Newest messages are kept and order is preserved.
- If the cut would start with an assistant reply (its question was cut off), that orphaned reply is dropped so history starts with a complete turn. (With an odd N you may therefore send N−1 messages.)
- The full history stays stored; only what is sent is trimmed.

**Token control:** fewer messages sent = fewer input tokens, lower cost and latency, and no overflow of the model's context limit.
**What is lost:** facts mentioned only in older, trimmed messages (e.g. your name from 20 messages ago) are forgotten. Raise the limit or add summarisation to mitigate this.

*Optional enhancement (not implemented):* when messages are about to be trimmed, ask the model to fold them into a short running summary, and send that summary as an extra system message ahead of the recent messages. Exact token counting could use the `tiktoken` package; it is deliberately not a required dependency.

## 13. Error handling and security

| Situation | HTTP status |
|---|---|
| Invalid JSON, empty message, missing/invalid conversation ID, message > 4000 chars | 400 |
| Rate limit / no quota | 429 |
| Missing API key or model, unknown model | 500 |
| Rejected API key | 502 |
| Empty/invalid model response, other API failures | 502 |
| Network error | 503 |
| Timeout | 504 |
| Unexpected server bug | 500 (generic message) |

All errors are JSON: `{"error": "readable message"}`. Raw SDK exceptions and stack traces are never sent to the user, and the key is never logged. The SDK uses a request timeout and one automatic retry. The API key is read from `.env` on the server only. `.env` is in `.gitignore`; `.env.example` holds placeholders. The frontend renders text with `textContent`, so HTML in messages cannot execute. Flask runs with `debug=False`.

## 14. API documentation

**`POST /api/conversations`** — start a conversation
Response `201`: `{"conversation_id": "conv_3f9a..."}`

**`POST /api/conversations/<conversation_id>/clear`** — erase its messages
Response `200`: `{"conversation_id": "conv_3f9a...", "history_messages": 0}`

**`POST /api/chat`**
Request:
```json
{"conversation_id": "conversation_123", "message": "My name is Sam and I am studying computer science."}
```
Response `200`:
```json
{"conversation_id": "conversation_123", "reply": "Nice to meet you, Sam! ...", "history_messages": 2}
```
`history_messages` is the total number of stored messages in that conversation. A new, valid, unseen conversation ID is created automatically.
Error example `400`: `{"error": "Message cannot be empty."}`

## 15. Testing

```powershell
pytest -v
```

Automated tests (the LLM is mocked, so no key or credits are needed):

| Test | File |
|---|---|
| 1 Basic call | `test_chat_api.py::test_basic_chat_returns_reply` |
| 2 Memory (Sam / computer science / ML) | `test_memory_earlier_messages_reach_the_model` |
| 3 Isolation | `test_conversations_are_isolated` |
| 4 Context window + system prompt kept | `test_context_window_truncates_but_keeps_system_prompt`, `test_conversation_manager.py` |
| 5 Missing message | `test_empty_message_is_rejected` |
| 6 API failure | `test_llm_error_returns_controlled_response`, `test_llm_service.py` |
| 7 New conversation | `test_new_conversation_starts_with_empty_history` |

**Real integration test** (calls OpenAI, may use paid credits; needs a valid `.env`):

```powershell
$env:RUN_INTEGRATION = "1"
pytest tests/test_integration_real_api.py -v -s
Remove-Item Env:RUN_INTEGRATION
```

**Manual test:** in the browser send "My name is Sam." → "I am studying computer science." → "I am interested in machine learning." → "What is my name, and what am I studying?" and check the answer. Then click **New Chat** and ask "What is my name?" — the bot should not know. To see an error state, temporarily blank `OPENAI_API_KEY`, restart, and send a message.

## 16. Known limitations

- In-memory storage (lost on restart; single process only).
- Truncation is by message count, not tokens, so very long messages can still use many tokens.
- Replies arrive all at once (no streaming).
- No user accounts; anyone who can reach the server can use your API key's quota.
- Concurrent requests to the same conversation are not specially ordered.

## 17. Future enhancements

Persistent storage (SQLite), token-based trimming with `tiktoken`, running summaries of old messages, streaming responses, Markdown/code rendering with a sanitiser, authentication and rate limiting, a conversation list in the UI.

## 18. Upload to GitHub

> ⚠️ **Never commit your real `.env` file or API key.** Anyone who sees it can spend your credits. If you ever commit a key by mistake, revoke it immediately on the OpenAI API keys page.

```powershell
git init
git status                      # .env must NOT appear in this list
git check-ignore -v .env        # should print the .gitignore rule that ignores .env
git add .
git status                      # review again: .env.example yes, .env no
git ls-files                    # shows exactly what is tracked
git commit -m "Initial commit: LLM chatbot with memory and context management"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Create the empty repository on GitHub first (without a README) and replace the URL placeholder.
