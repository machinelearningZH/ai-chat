from _core.utils import load_config


_MESSAGES = load_config()["messages"]

WELCOME = _MESSAGES["welcome"].strip()
SYSTEM_PROMPT = _MESSAGES["system_prompt"].strip()

HORIZONTAL_LINE = "\n\n" + ("-" * 80) + "\n\n"

# We repeat the user's document task after the attached content because smaller
# local models can lose the original instruction in long contexts.
DOCUMENT_PROCESSING_TEMPLATE = _MESSAGES["document_processing_template"].strip()
DOCUMENT_ITEM_TEMPLATE = _MESSAGES["document_item_template"].strip()
DOCUMENT_ERROR_TEMPLATE = _MESSAGES["document_error_template"]
DOCUMENT_LIMIT_WARNING = _MESSAGES["document_limit_warning"]
DOCUMENT_SUCCESS = _MESSAGES["document_success"]
DOCUMENT_PROCESSING_STATUS = _MESSAGES["document_processing_status"]
CONTEXT_TRIMMED = _MESSAGES["context_trimmed"]
MESSAGE_TOO_LARGE = _MESSAGES["message_too_large"]
LLM_ERROR = _MESSAGES["llm_error"]
