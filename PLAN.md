# Open work

- Verify streaming, retries, reconnects, and the Stop button in the browser
  with Ollama, vLLM, and llama.cpp.
- Exercise Docling with Office and HTML fixtures.
- Verify stats volume write access and run `make stats` (including
  `STATS_SOURCE=compose` and `STATS_SOURCE=native`) before and after stopping
  the Compose app.
- Verify the repository's dependency monitoring settings and add container
  image scanning to CI.

## Document generation

- Add an **Als Word herunterladen** action to completed replies. Export the
  reviewed text as an editable `.docx` using a neutral template that supports
  headings, paragraphs, lists, and tables. Render the file locally from the
  existing reply and serve it as a Chainlit attachment.
- The local feasibility check created and reopened a Word file with headings,
  a list, and a table, then verified that Chainlit stored the attachment.
  `python-docx` is already installed through Docling. Declare it as a direct
  dependency when the app starts using it.
- Test that the browser downloads the correct reply as a readable Word file.
  Bound export size and verify that downloads are scoped to the originating
  chat session and expire with it.
- If users need to request Excel workbooks or PowerPoint decks directly,
  evaluate Amtschat's approach of validating streamed model tool calls and
  rendering files locally. Verify tool-call support with Ollama, vLLM, and
  llama.cpp, and confirm reuse rights before copying code or templates.
