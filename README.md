# DocIntel

DocIntel is a Dockerized document-intelligence system for PDF, image, Excel, and CSV invoices. It extracts OCR/text, structured invoice data, evidence, validation issues, and searchable document records.

## Requirements

- Docker Desktop with Compose
- An OpenAI API key for live extraction and embeddings

## Setup

```powershell
Copy-Item backend\.env.example backend\.env
# Edit backend\.env and set OPENAI_API_KEY
docker compose up --build
```

- Web UI: <http://localhost:3000>
- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Set `API_KEY` in `backend/.env` to require `X-API-Key` on API requests. Do not commit `backend/.env`.

## Usage

Upload one or more supported files in the UI, select a document, and review processing status, extracted fields, evidence, OCR pages, validation issues, corrections, and processing history. Failed documents can be reprocessed from the document list or detail view.

The API uses:

- `POST /api/documents` for multipart uploads
- `GET /api/documents` and `GET /api/documents/{id}` for status
- `GET /api/documents/{id}/result` for extraction and validation
- `GET /api/documents/{id}/pages` for OCR/text
- `PATCH /api/documents/{id}/corrections` for corrections
- `POST /api/documents/{id}/approve` to approve reviewed data
- `POST /api/documents/{id}/reprocess` and `/api/documents/reprocess-failed`
- `GET /api/search?mode=keyword|semantic&q=...` for search

## Testing

```powershell
docker compose run --rm --workdir /code api pytest -q
Set-Location frontend
npm.cmd test -- --run
npm.cmd run build
```

The backend tests use deterministic fakes; live LLM accuracy requires the evaluation workflow and credentials described in [`docs/EVALUATION_REPORT.md`](docs/EVALUATION_REPORT.md).

Run the checked-in processing evaluation in Docker:

```powershell
docker compose run --rm -v "${PWD}:/workspace" --workdir /workspace api python evaluation/run.py
```

## Architecture and deliverables

- [`docs/architecture.mmd`](docs/architecture.mmd)
- [`docs/DB_SCHEMA.sql`](docs/DB_SCHEMA.sql)
- [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md)
- [`docs/AI_ASSISTED_DEVELOPMENT.md`](docs/AI_ASSISTED_DEVELOPMENT.md)
- [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md)
- [`evaluation/`](evaluation/)
