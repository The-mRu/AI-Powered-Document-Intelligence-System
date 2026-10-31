# DocIntel

DocIntel is a Dockerized document-intelligence system for PDF, image, Excel, and CSV invoices. It extracts OCR/text, structured invoice data, evidence, validation issues, and searchable document records.

## 🚀 Live Demo

**Try DocIntel:** [Open Live Application](https://docintel-frontend-azure.vercel.app/)

**Backend API:** [Open API](https://docintel-api-2shu.onrender.com/)

**API Documentation:** [Swagger UI](https://docintel-api-2shu.onrender.com/docs)

> **Note:** The backend is hosted on Render's free tier and may take approximately a minute to
> wake up after inactivity. The first request may be slower than subsequent requests.

## Key features

- OCR and structured invoice extraction for PDF, image, Excel, and CSV documents
- Evidence traceability, validation issues, and review status
- Multi-document upload and processing status monitoring
- Search, corrections, approval, reprocessing, and original-file download
- Local Docker development and production deployment configuration

## Architecture

See the [architecture diagram](docs/architecture.mmd) and
[architecture and deployment guide](docs/ARCHITECTURE_AND_DEPLOYMENT_GUIDE.md) for the detailed
component and deployment design.

## Technology stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery
- **Frontend:** React, Vite
- **Document processing:** OCR, PDF/image processing, pandas spreadsheet parsing
- **AI:** OpenAI API for invoice extraction and configured semantic embeddings
- **Production services:** Vercel, Render, Supabase PostgreSQL/Storage

## Supported document formats

- PDF, including digital and scanned documents
- JPG, PNG, and TIFF images
- XLSX and XLS spreadsheets
- CSV files

## System workflow

1. Upload a supported document.
2. Extract text using native parsing or OCR.
3. Extract structured invoice data through the configured OpenAI model.
4. Verify evidence and validate financial values.
5. Store results and processing history.
6. Review, search, correct, approve, or download the original document.

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

The portfolio demo is intentionally public and does not use application API-key authentication. Keep
`backend/.env` private and never commit it; it contains the backend-only OpenAI, database, Redis,
and optional Supabase service-role settings.

## 🌐 Deployment Architecture

DocIntel is deployed using the following services:

| Component | Platform | Purpose |
|---|---|---|
| Frontend | Vercel | React application hosting |
| Backend | Render | FastAPI application hosting |
| Database | Supabase | PostgreSQL with pgvector |
| File Storage | Supabase Storage | Original document storage |
| AI Processing | OpenAI API | Invoice information extraction |

### Production URLs

- Frontend: [https://docintel-frontend-azure.vercel.app/](https://docintel-frontend-azure.vercel.app/)
- Backend: [https://docintel-api-2shu.onrender.com/](https://docintel-api-2shu.onrender.com/)
- API Documentation: [https://docintel-api-2shu.onrender.com/docs](https://docintel-api-2shu.onrender.com/docs)

### Deployment configuration

**Frontend**

- Framework: React with Vite
- Hosting: Vercel
- Build command: `npm run build`
- Output directory: `dist`
- Environment variable: `VITE_API_BASE`

**Backend**

- Framework: FastAPI
- Hosting: Render with Docker
- Database: Supabase PostgreSQL
- File storage: Supabase Storage
- Processing mode: FastAPI BackgroundTasks

### Important deployment notes

- The Render free-tier backend may spin down after inactivity, resulting in cold starts.
- BackgroundTasks are not durable job queues; an instance restart can interrupt processing.
- OpenAI API usage may incur charges.
- Production credentials are stored as server-side environment variables and are not committed
  to the repository.

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

## Database schema

The database design is documented in [`docs/DB_SCHEMA.sql`](docs/DB_SCHEMA.sql).

## Architecture and deliverables

- [`docs/architecture.mmd`](docs/architecture.mmd)
- [`docs/DB_SCHEMA.sql`](docs/DB_SCHEMA.sql)
- [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md)
- [`docs/AI_ASSISTED_DEVELOPMENT.md`](docs/AI_ASSISTED_DEVELOPMENT.md)
- [`docs/ai-disclosure/AI_USAGE_DISCLOSURE.md`](docs/ai-disclosure/AI_USAGE_DISCLOSURE.md)
- [`docs/ai-disclosure/AI_PROMPTS.md`](docs/ai-disclosure/AI_PROMPTS.md)
- [`docs/ai-disclosure/AI_ASSISTED_WORK_LOG.md`](docs/ai-disclosure/AI_ASSISTED_WORK_LOG.md)
- [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md)
- [`evaluation/EVALUATION_REPORT.md`](evaluation/EVALUATION_REPORT.md)
- [`evaluation/`](evaluation/)

### AI disclosure

The AI disclosure documents distinguish AI-assisted development from the OpenAI-powered
document extraction functionality used by the application:

- [AI usage disclosure](docs/ai-disclosure/AI_USAGE_DISCLOSURE.md)
- [Representative AI prompts](docs/ai-disclosure/AI_PROMPTS.md)
- [AI-assisted work log](docs/ai-disclosure/AI_ASSISTED_WORK_LOG.md)

## Future improvements

- Use a durable production job queue for hosted processing.
- Add authentication and per-user ownership if the application evolves beyond a shared demo.
- Expand the labeled evaluation dataset and improve extraction normalization for regional number
  formats.
