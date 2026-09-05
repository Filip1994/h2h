# v2.1 change log

- `src/quantbot/engine.py`: explicit point-in-time cutoff; cache key includes cutoff; H2H neutral/optional; rejection reasons; richer prediction audit fields.
- `src/quantbot/risk.py`: cumulative daily stake budget; separate open exposure; daily analytics.
- `src/quantbot/types.py`: decision/data cutoff and neutral `DC_VALUE` bet type.
- `src/quantbot/config.py`: `H2H_TELEMETRY_ENABLED`.
- `src/quantbot/reporting.py`: simpler daily bulletin; no H2H as a decision input.
- `main.py`: richer ledger metadata/analytics.
- `.github/workflows/daily.yml`: explicit H2H telemetry variable.
- `.github/workflows/calibrate.yml`: valid workflow extension in the packaged project.
- `tests/test_engine_integration.py`: H2H neutrality and cache snapshot tests.
- `tests/test_risk_storage.py`: cumulative daily-risk test.
