# Test results

These results were run during the Phase 2 audit on 2026-10-30.

## Backend

Command:

```powershell
docker compose run --rm --workdir /code api pytest -q
```

Result: **117 passed, 7 warnings**.

## Frontend

Commands:

```powershell
Set-Location frontend
npm.cmd test -- --run
npm.cmd run build
```

Results: **11 frontend tests passed**; Vite production build completed successfully.

Warnings are existing pandas deprecation warnings from spreadsheet parsing. These results cover the repository state at the time of the run and should be refreshed after later changes.
