# AI-Assisted Work Log

This log records the major categories of AI-assisted work performed on DocIntel. It is a
summary of the development history, not a complete transcript. The developer reviewed,
integrated, tested, and verified the resulting changes.

## Architecture and pipeline review

- Reviewed the FastAPI, React, Docker, PostgreSQL, Redis/Celery, OCR, extraction, validation,
  storage, and search architecture.
- Preserved the existing local Docker/Celery workflow while preparing configurable deployment
  behavior.
- Documented the architecture and database schema for the assignment.

## Extraction and validation work

- Investigated extraction failures involving supplier/customer fields, evidence, percentages,
  quantities and units, line-item preservation, payment fields, and unreadable invoice fields.
- Added or reviewed regression coverage for extraction and financial validation behavior.
- Updated deterministic validation behavior to use decimal arithmetic, discount handling,
  reconciliation, tolerances, and structured mismatch reporting.

## Storage, API, and frontend work

- Reviewed backend storage paths and added support for retrieving original uploaded files
  through the backend without exposing storage credentials.
- Added the original-file viewing and download experience while preserving extracted data access.
- Configured frontend API access through `VITE_API_BASE` and preserved the public-demo model.
- Removed owner API-key authentication when the project requirements changed to a fully public
  portfolio demo; no user accounts or Supabase Auth were added.

## Deployment and security review

- Reviewed environment-variable handling, CORS, database and storage configuration, upload
  restrictions, and background-processing modes.
- Kept OpenAI, database, Redis, and Supabase service-role credentials backend-only.
- Documented free-hosting limitations and deployment steps without deploying the application.

## Evaluation and verification

- Added reproducible benchmark tooling for 15 valid documents and four separate expected-failure
  files.
- Verified the benchmark generation constraints and ran the valid-document evaluation three
  times per document.
- Recorded measured accuracy, processing success, review rate, token totals, latency,
  consistency, and estimated cost in the evaluation reports.
- Ran the backend and frontend test suites and the frontend production build. Existing pandas
  spreadsheet deprecation warnings were reported rather than silently suppressed.

## Developer responsibility

The developer made the final decisions about scope, architecture, security, correctness, and
acceptance. AI-generated suggestions were checked against the actual repository and validated
with tests or measured evaluation runs before being documented as completed work.

No claim is made here for AI tools, prompts, code contributions, test results, or performance
metrics that are not supported by the repository or its recorded verification results.
