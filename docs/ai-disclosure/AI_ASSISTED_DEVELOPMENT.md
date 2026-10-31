# AI-assisted development disclosure

DocIntel was developed with AI-assisted coding support. Human review remained responsible for requirements interpretation, architecture decisions, source validation, security decisions, and test-result verification.

AI assistance was used for code exploration, debugging, implementation suggestions, test generation, and documentation drafting. No API keys, `.env` files, or other secrets were supplied to the assistant or committed to the repository.

The authoritative implementation is the source code and tests in this repository. Generated suggestions were reviewed against the existing architecture and executed tests before being retained.

## Representative prompts

The following prompts summarize representative requests used during development. They are
examples, not a complete transcript, and should not be interpreted as verbatim conversation
records.

### 1. System architecture

> Act as a senior AI systems architect. Help design an AI-powered document intelligence system that processes PDF, image, Excel, and CSV files. The system should support OCR, structured invoice extraction, financial validation, document search, and a React frontend. Recommend a modular architecture and explain the trade-offs.

### 2. Document processing

> Review the document processing requirements. Design a Python pipeline that handles digital PDFs, scanned PDFs, JPG, PNG, TIFF, XLSX, XLS, and CSV files. Include multi-page documents, multiple spreadsheet sheets, corrupted files, and error handling.

### 3. OCR

> Help design an OCR pipeline for scanned business documents. Explain how to preprocess low-quality images, extract text, handle multi-page PDFs, and identify pages where OCR quality is poor.

### 4. AI information extraction

> Design a reliable invoice extraction prompt that converts OCR text into structured JSON. Extract invoice number, date, supplier, customer, subtotal, tax, total, currency, and line items. Do not invent missing values. Represent uncertain or missing fields explicitly.

### 5. Financial validation

> Review the invoice validation logic. Identify how to validate line-item totals, percentage discounts, fixed discounts, subtotal, tax, shipping, trade discounts, and grand totals. Use Decimal arithmetic and account for rounding tolerance. Suggest edge cases and automated tests.

### 6. Backend API

> Review the REST API architecture for document uploads, processing status, extracted results, document search, manual corrections, and failed-job reprocessing. Recommend appropriate validation, error handling, and background processing.

### 7. Database and search

> Design a relational database schema for a document intelligence application. It should store document metadata, extracted text, invoice data, line items, validation errors, processing history, and search-related information.

### 8. Frontend

> Help design a React interface for uploading multiple documents, monitoring processing status, inspecting extracted invoice data, editing fields, and searching processed documents.

### 9. Testing and evaluation

> Create a testing strategy for document processing, OCR, spreadsheet parsing, AI extraction, financial validation, API endpoints, and failure scenarios. Suggest measurable evaluation metrics and explain how to calculate them using a labeled dataset.

### 10. Deployment and debugging

> Review the deployment architecture for a FastAPI and React document intelligence application using Docker, PostgreSQL, Redis, and cloud hosting. Identify configuration issues, security risks, and deployment verification steps.

These prompts were reconstructed as representative summaries where an exact original prompt was
not retained; no prompt is claimed to be verbatim unless explicitly preserved in project history.
