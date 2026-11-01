"""Flask backend for the Engineering AI Assistant."""

import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from services.conversation_manager import ConversationManager, is_valid_conversation_id
from services.llm_service import SYSTEM_PROMPT, LLMError, LLMService

# Read variables from a local .env file (if present) into the environment.
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_MAX_HISTORY_MESSAGES = 10
MAX_USER_MESSAGE_CHARS = 4000


def read_max_history_messages():
    """Read MAX_HISTORY_MESSAGES from the environment (default 10, minimum 2)."""
    raw_value = os.getenv("MAX_HISTORY_MESSAGES", str(DEFAULT_MAX_HISTORY_MESSAGES))
    try:
        return max(2, int(raw_value))
    except ValueError:
        logger.warning("Invalid MAX_HISTORY_MESSAGES; using %d", DEFAULT_MAX_HISTORY_MESSAGES)
        return DEFAULT_MAX_HISTORY_MESSAGES


def error_response(message, status_code):
    """Return a JSON error in one consistent shape."""
    return jsonify({"error": message}), status_code


def create_app(llm_service=None, conversation_manager=None, max_history_messages=None):
    """Application factory. The arguments let tests inject fakes."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # reject huge request bodies

    llm = llm_service or LLMService()
    conversations = conversation_manager or ConversationManager()
    history_limit = max_history_messages or read_max_history_messages()

    problem = llm.config_problem() if hasattr(llm, "config_problem") else None
    if problem:
        logger.warning("%s - chat requests will fail until .env is configured.", problem)

    # ------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return render_template("index.html")

    # ----------------------------------------------------- conversations
    @app.post("/api/conversations")
    def new_conversation():
        """Start a fresh conversation and return its unique ID."""
        return jsonify({"conversation_id": conversations.create_conversation()}), 201

    @app.post("/api/conversations/<conversation_id>/clear")
    def clear_conversation(conversation_id):
        """Erase all messages of one conversation."""
        if not is_valid_conversation_id(conversation_id):
            return error_response("Invalid conversation ID.", 400)
        conversations.clear(conversation_id)
        return jsonify({"conversation_id": conversation_id, "history_messages": 0})

    # --------------------------------------------------------------- chat
    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return error_response("Request body must be valid JSON.", 400)

        conversation_id = payload.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return error_response("conversation_id is required.", 400)
        conversation_id = conversation_id.strip()
        if not is_valid_conversation_id(conversation_id):
            return error_response(
                "conversation_id is invalid. Use only letters, numbers, '_' or '-' (max 64 characters).", 400)

        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            return error_response("Message cannot be empty.", 400)
        message = message.strip()
        if len(message) > MAX_USER_MESSAGE_CHARS:
            return error_response(
                f"Message is too long (maximum {MAX_USER_MESSAGE_CHARS} characters).", 400)

        # System prompt + newest history + this message (see conversation_manager).
        llm_messages = conversations.build_context(
            conversation_id, message, history_limit, SYSTEM_PROMPT)

        try:
            reply = llm.generate_reply(llm_messages)
        except LLMError as exc:
            return error_response(exc.user_message, exc.status_code)
        except Exception:
            logger.exception("Unexpected error while generating a reply")
            return error_response("Something went wrong on the server. Please try again.", 500)

        # Save the turn only after the model answered successfully.
        total_messages = conversations.add_turn(conversation_id, message, reply)
        return jsonify({
            "conversation_id": conversation_id,
            "reply": reply,
            "history_messages": total_messages,
        })

    # ------------------------------------------------------ JSON errors
    @app.errorhandler(404)
    def not_found(_error):
        return error_response("Not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return error_response("Method not allowed.", 405)

    @app.errorhandler(413)
    def too_large(_error):
        return error_response("Request is too large.", 413)

    @app.errorhandler(500)
    def server_error(_error):
        return error_response("Something went wrong on the server. Please try again.", 500)

    return app


app = create_app()

if __name__ == "__main__":
    # debug=False so stack traces are never shown in the browser.
    app.run(host="127.0.0.1", port=5000, debug=False)
