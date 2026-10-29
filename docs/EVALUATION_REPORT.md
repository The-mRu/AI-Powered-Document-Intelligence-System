# Evaluation report

## Scope and method

The checked-in evaluation set contains two real samples:

- `backend/samples/invoice-sample.pdf`
- `backend/samples/Standard Grocery Bill.jpg`

Run from the repository root:

```powershell
python evaluation\run.py
```

The runner measures document routing, page count, required OCR/text markers, elapsed processing time, and processing success rate. It does not call the LLM.

## Results

Measured on 2026-10-30 in the project Docker environment:

| Sample | Routing | Pages | Text checks | Processing time |
|---|---:|---:|---:|---:|
| `invoice-sample.pdf` | PASS | PASS (1) | PASS | 96.47 ms |
| `Standard Grocery Bill.jpg` | PASS | PASS (1) | PASS | 2297.23 ms |

Processing/routing success rate: **2/2 (100%)**. Mean measured processing time: **1196.85 ms** for this two-document run. These are sample processing measurements, not production throughput or an extraction-accuracy claim. The raw run is saved as `evaluation/results.json`.

## Limitations

This repository does not contain a labeled field-level dataset for invoice number, dates, party fields, amounts, or line items. Therefore extraction accuracy, precision, recall, and F1 are not reported. Live LLM latency and throughput are also environment- and provider-dependent.

To complete the assignment evaluation, add a representative labeled dataset, run the application with production-like credentials, and record field-level accuracy, processing latency, throughput, document success rate, and failure rate with the dataset version and environment.
