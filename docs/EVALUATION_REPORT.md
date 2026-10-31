# Evaluation report

The completed extraction benchmark report is maintained at
[`evaluation/EVALUATION_REPORT.md`](../evaluation/EVALUATION_REPORT.md).

## Measured summary

- 15 valid documents: 8 PDFs, 4 degraded images, 2 XLSX, and 1 CSV.
- 45 valid extraction runs: 3 runs per document.
- 4 expected-failure files run separately.
- Overall field accuracy: 95.37%.
- Valid processing success: 45/45 (100%).
- Needs-review rate: 20/45 (44.44%).
- Input tokens: 71,532.
- Output tokens: 35,043.
- Estimated OpenAI cost: $0.031756 using the dated rates in
  [`evaluation/pricing.json`](../evaluation/pricing.json).

The detailed report includes per-field accuracy, hallucinations, missing values,
line-item metrics, latency percentiles, run consistency, and expected-failure
outcomes.
