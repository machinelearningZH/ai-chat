# Maintenance notes

- A chat counts when its first message arrives. Later chat totals use the same
  Chainlit session, which is kept for 60 seconds after a disconnect. Counting
  at disconnect would count the same chat again after a reconnect.
- A message counts before the model request. A stopped reply therefore counts
  as a message without a completed reply or a model error. The report includes
  it in "Not answered".
- The app checks that it can write usage statistics before serving the chat.
  Later write failures go to the app log so a storage problem does not discard
  an answer. The report opens the database read-only and can run without model
  credentials.
- The report counts waiting for the first reply text separately from the time
  spent streaming the rest. The speed figure divides all reply tokens by the
  time from the first reply text to the end.
- In test setup files, import the app inside fixtures. Importing it when
  pytest first loads those files can read the developer's config and
  credentials before pytest sets up its temporary environment.
