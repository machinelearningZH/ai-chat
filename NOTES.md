# Maintenance notes

## Usage statistics

- Count a chat on its first message. Chainlit can reuse the session after a
  reconnect, so counting disconnects would inflate chat totals. Chat-length
  counters record when each threshold is reached, which can fall on a later
  day than the first message.
- Count the message before requesting a reply. A stopped reply contributes to
  “Not answered” without adding a completed reply or model error. The report
  measures streaming speed from the first reply text to the end of the stream.
- The app checks write access at import because Chainlit can continue serving
  after a startup hook fails. Later storage errors are logged so the chat can
  continue. The report uses a read-only snapshot and runs without model keys.
