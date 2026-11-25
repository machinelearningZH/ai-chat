# Open work

- Test a chat in the browser against each supported model server. Check streamed
  replies, retries, reconnects, and the Stop button. Current tests use a stand-in
  for the model server.
- Test Docling with representative Office and HTML files. Upload tests
  currently cover plain text and PDF text extraction.
- Define and test what happens when several imports are queued, when an import
  or reply is cancelled, and when two messages arrive in the same chat.
- Check how configuration handles extra or malformed template fields and
  numbers such as infinity.
- Test the usage report with Compose running and stopped, including write
  access to the stats volume. CI checks Compose configuration and whether the
  image serves the chat page.
- Verify the repository's dependency monitoring settings and add container
  image scanning to CI.
