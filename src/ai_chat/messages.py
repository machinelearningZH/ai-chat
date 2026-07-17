from ai_chat.config import load_config


_MESSAGES = load_config()["messages"]

WELCOME = _MESSAGES["welcome"].strip()
SYSTEM_PROMPT = _MESSAGES["system_prompt"].strip()

HORIZONTAL_LINE = "\n\n" + ("-" * 80) + "\n\n"

# Repeating the task after document content helps smaller local models retain it.
DOCUMENT_PROCESSING_TEMPLATE = _MESSAGES["document_processing_template"].strip()
DOCUMENT_ITEM_TEMPLATE = _MESSAGES["document_item_template"].strip()
DOCUMENT_ERROR_TEMPLATE = _MESSAGES["document_error_template"]
DOCUMENT_LIMIT_WARNING = _MESSAGES["document_limit_warning"]
DOCUMENT_SUCCESS = _MESSAGES["document_success"]
DOCUMENT_PARTIAL_SUCCESS = _MESSAGES["document_partial_success"]
DOCUMENT_FAILURE = _MESSAGES["document_failure"]
DOCUMENT_PROCESSING_STATUS = _MESSAGES["document_processing_status"]
CONTEXT_TRIMMED = _MESSAGES["context_trimmed"]
MESSAGE_TOO_LARGE = _MESSAGES["message_too_large"]
LLM_ERROR = _MESSAGES["llm_error"]
