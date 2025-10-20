WELCOME = """
Willkommen zum AI-Chat! Du kannst mir Fragen stellen oder Anweisungen geben, und ich werde mein Bestes tun, um dir zu helfen. Du kannst auch Dokumente anhängen, die ich bei der Beantwortung deiner Fragen berücksichtigen soll.
""".strip()


SYSTEM_PROMPT = """
Du bist ein hilfreicher Assistent.
""".strip()


HORIZONTAL_LINE = "\n\n" + ("-" * 80) + "\n\n"


# We noticed that OSS LLMs often tend to forget instructions that are given only once at the beginning if long context follows, e.g. when documents are attached.
# Therefore, we repeat the instructions at the end to make sure the model follows them.
DOCUMENT_PROCESSING_TEMPLATE = """
Du erhältst vom Nutzer ein oder mehrere Dokumente, die du bearbeiten sollst. Du sollst folgendes mit den Dokumenten tun: {instructions}

Hier sind die Dokumente:
{documents}
{horizontal_line}

Führe jetzt die Anweisungen aus:
{instructions}
""".strip()


DOCUMENT_ITEM_TEMPLATE = """
{horizontal_line}
Dateiname: {filename}

Dateiinhalt:
{content}

{horizontal_line}
""".strip()


DOCUMENT_ERROR_TEMPLATE = """

## Dokument: {filename}
Das Dokument konnte nicht verarbeitet werden.
[Fehler beim Verarbeiten: {error}]
"""


DOCUMENT_LIMIT_WARNING = """⚠️ Die Dokumente enthalten zu viel Text. Ich lasse {element_name} weg."""


DOCUMENT_SUCCESS = """Ich habe die Dokumente importiert. Ich bearbeite deine Anfrage."""


DOCUMENT_PROCESSING_STATUS = "📄 Ich importiere deine Dokumente..."


CONTEXT_TRIMMED = "⚠️ Die Textmenge in unserem Chat ist zu gross geworden. Ich entferne Nachrichten vom Anfang unseres Chats."
