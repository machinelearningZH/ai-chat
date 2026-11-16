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
