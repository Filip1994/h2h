# Settlement Self-Healing

## Scope

The settlement watchdog is a production orchestration layer. It does not implement settlement logic and does not change the betting or selection contract.

## Flow

1. `monitor.yml` remains the only settlement executor: `main.py monitor` -> `settle_alerts.py` -> settlement health -> ledger commit.
2. `settlement-watchdog.yml` runs every 10 minutes and checks `settlement_health.py --max-age-minutes 30`.
3. Healthy state is a NO-OP.
4. If stale PENDING settlements are detected, the watchdog first checks whether an existing `monitor.yml` run is already queued/in progress.
5. If an active monitor resolves the stale state, the watchdog exits without starting another run.
6. Otherwise it dispatches the existing `monitor.yml`, waits for that recovery run, and rechecks settlement health from `origin/main`.
7. Recovery failure or timeout causes the watchdog to fail explicitly.

## Race safety

`monitor.yml` retains the `quantbet-ledger` concurrency group with `cancel-in-progress: false`. The watchdog has a separate concurrency group because it never mutates the ledger itself. Recovery is performed only by `monitor.yml`, so watchdog overlap cannot create a second settlement executor.

## Acceptance coverage

- Normal healthy state: watchdog NO-OP.
- Stale PENDING after scheduler miss: watchdog dispatches `monitor.yml` and requires health recovery.
- Delayed monitor: watchdog waits for an active monitor and avoids a duplicate recovery dispatch when that run resolves the stale state.
- Recovery failure/timeout: watchdog fails explicitly.
- Repeated watchdog runs after settlement: health is OK and no recovery is dispatched.
- Monitor/watchdog overlap: monitor remains protected by the existing ledger concurrency lock.
- No changes to settlement rules, result logic, betting engine, selection, H2H, EV/edge, calibration, odds, risk/Kelly/stake, intraday selection, or CLV.

## Operational note

The watchdog itself uses GitHub's scheduler, so this adds recovery for missed/delayed `monitor.yml` executions but does not claim that GitHub scheduled execution is mathematically guaranteed. An external scheduler would be a separate hardening option.
