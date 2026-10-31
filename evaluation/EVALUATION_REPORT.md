# Extraction benchmark report

## Scope
- Valid documents: 15; recorded valid runs: 45.
- Composition: 8 digital PDFs, 4 degraded images, 3 spreadsheets.
- Expected-failure files: 4; separate runs recorded: 4.
- Repeated runs are measurements of the same document, not additional documents.

## Accuracy and error metrics
- Overall field accuracy: 1585/1662 = 95.37% (denominator: non-null ground-truth scalar and line-item fields).
- Hallucinations: 75 incorrect non-null predictions.
- Missing predictions: 2.
- Expected-null correctness: 159/159.
- Needs-review rate: 20/45 = 44.44%.

| Field | Correct | Applicable | Accuracy | Missing | Hallucinations |
|---|---:|---:|---:|---:|---:|
| invoice_number | 45 | 45 | 100.00% | 0 | 0 |
| invoice_date | 45 | 45 | 100.00% | 0 | 0 |
| supplier_name | 45 | 45 | 100.00% | 0 | 0 |
| customer_name | 45 | 45 | 100.00% | 0 | 0 |
| subtotal | 36 | 45 | 80.00% | 0 | 9 |
| tax | 36 | 45 | 80.00% | 0 | 9 |
| discount | 27 | 30 | 90.00% | 0 | 3 |
| total | 36 | 45 | 80.00% | 0 | 9 |
| currency | 40 | 42 | 95.24% | 2 | 0 |
| shipping | 12 | 12 | 100.00% | 0 | 0 |
| other_charges | 6 | 9 | 66.67% | 0 | 3 |
| payments_received | 9 | 9 | 100.00% | 0 | 0 |
| balance_due | 9 | 9 | 100.00% | 0 | 0 |
| line_item_fields | 1194 | 1236 | 96.60% | 0 | 42 |

## Reliability and latency
- Valid-document processing success: 45/45 = 100.00%.
- Run-to-run exact-result consistency: 10/15 documents.
- pdf processing latency: p50=6198.8 ms; p95=8093.43 ms; n=24.
- image processing latency: p50=8775.76 ms; p95=16129.02 ms; n=12.
- spreadsheet processing latency: p50=7466.39 ms; p95=8640.86 ms; n=9.

## Token usage and cost
- Models observed: gpt-4o-mini.
- Input tokens: 71532; output tokens: 35043.
- Estimated API cost: $0.031756 (requires provider usage and an explicit local pricing.json with pricing date).

## Ten worst misses
| Filename | Field | Expected | Actual |
|---|---|---|---|
| invoice-01.pdf | subtotal | 171.25 | 17125 |
| invoice-01.pdf | tax | 34.25 | 3425 |
| invoice-01.pdf | total | 170.19 | 17019 |
| invoice-01.pdf | other_charges | 7.50 | 750 |
| invoice-01.pdf | subtotal | 171.25 | 17125 |
| invoice-01.pdf | tax | 34.25 | 3425 |
| invoice-01.pdf | total | 170.19 | 17019 |
| invoice-01.pdf | other_charges | 7.50 | 750 |
| invoice-01.pdf | subtotal | 171.25 | 17125 |
| invoice-01.pdf | tax | 34.25 | 3425 |

Expected-failure outcomes are stored separately in `extraction_expected_results.json` and are excluded from valid-document accuracy denominators.
