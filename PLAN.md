# Remaining test risks

- Real model-server HTTP/SSE compatibility, SDK retry behavior, and Chainlit browser
  interactions remain unverified; current streaming coverage ends at the SDK call.
- Docling conversion and its model assets were not exercised. PDF tests use the
  production PyMuPDF path without downloads.
- Conversion semaphore saturation, cancellation, simultaneous messages in one
  session, and stream resource cleanup need explicit lifecycle/concurrency
  contracts before adding assertions. No concurrent-message guarantee is documented.
- Template validation for malformed or extra placeholders and non-finite numeric
  settings needs a focused configuration-contract review. No behavior was changed
  or failing assertion suppressed for these untested cases.
- Docker/Compose builds, container smoke checks, accelerator configurations, and
  launch scripts were not executed locally in this audit; existing CI checks remain.
- Third-party deprecation warnings (Traceloop/Pydantic and PyMuPDF bindings) remain
  visible. Dependency upgrades and migration away from `fitz` are outside this task.

# Usage statistics

- A stopped answer counts as a message without a response or a model error; this is
  tested with a cancelled stream, not with Chainlit's stop button. The report shows
  such messages only as the unnamed rest of its "Not answered" line.
- The Docker path was not run locally: `make stats` through Compose, the ownership of
  the `usage-stats` volume, and the container start with the write check. CI starts
  the container without a volume.

# Dependency monitoring

- Dependabot, checked 2026-11-19: the repository setting "Dependabot security updates"
  is disabled and no `.github/dependabot.yml` exists. The two pull requests of
  2026-02-11 were security updates. AGENTS.md asks for dependency monitoring to stay
  enabled.
