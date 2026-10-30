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
| `invoice-sample.pdf` | PASS | PASS (1) | PASS | 266.98 ms |
| `Standard Grocery Bill.jpg` | PASS | PASS (1) | PASS | 5028.39 ms |

Processing/routing success rate: **2/2 (100%)**. Mean measured processing time: **2647.69 ms** for this two-document run. These are sample processing measurements, not production throughput or an extraction-accuracy claim. The raw run is saved as `evaluation/results.json`.

## Limitations

The evaluation checks routing, page count, OCR/text markers, elapsed processing time, and processing success only. It does not measure structured extraction accuracy. This repository does not contain a labeled field-level dataset for invoice number, dates, party fields, amounts, or line items; therefore extraction accuracy, precision, recall, and F1 are not reported. Live LLM latency and throughput are also environment- and provider-dependent.

The measured **routing/text-processing success rate is 2/2 (100%)** and the measured **processing failure rate is 0/2 (0%)** for this two-sample run. These values must not be interpreted as invoice extraction accuracy or production reliability. A representative labeled dataset and production-like evaluation run would be required to report field-level accuracy, throughput, and representative success/failure metrics.
