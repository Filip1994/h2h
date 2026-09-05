# Migration from main to v2.1 hardening

1. Keep `bets.json`, `predictions.json` and existing ledger history.
2. Replace the Python source, tests and `.env.example` with this package.
3. Ensure `.github/workflows/calibrate.yml` exists and remove the old typo `.github/workflows/calibrate.ym` if it exists in the target repository.
4. Set repository variable `H2H_TELEMETRY_ENABLED=false` for normal production operation.
5. Keep `PAPER_MODE=true` until the OOS validation gate is satisfied.
6. Do not edit historical bet records to make the new schema fit; old records remain valid legacy observations.

The GitHub connector used for this session can read the repository but currently rejects branch/ref writes with HTTP 403. Therefore this package is prepared locally rather than silently pushing changes to `main`.
