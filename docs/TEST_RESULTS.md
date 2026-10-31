# Test results

These results were run in the Docker Compose environment on 2026-10-31.

## Backend

Command:

```powershell
docker compose run --rm --workdir /code api pytest -q
```

Result: **136 passed, 7 warnings**.

## Frontend

Commands:

```powershell
Set-Location frontend
npm.cmd test -- --run
npm.cmd run build
```

Results: **14 frontend tests passed**; Vite production build completed successfully.

Warnings are existing pandas Excel deprecation warnings from spreadsheet parsing.

## Extraction benchmark

The isolated benchmark ran 15 valid documents three times each:

- 45 valid runs completed successfully.
- 95.37% overall field accuracy.
- 44.44% needs-review rate.
- 71,532 input tokens and 35,043 output tokens.
- Estimated cost: $0.031756 using the documented local pricing metadata.
- Four expected-failure files were run separately and failed as expected.

Detailed field, latency, consistency, and cost results are in
[`evaluation/EVALUATION_REPORT.md`](../evaluation/EVALUATION_REPORT.md).
