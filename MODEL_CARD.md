# Model card

- **Version:** `dc-v2.0.0`
- **Default mode:** paper trading
- **Prediction target:** full-time 90-minute score-derived binary markets
- **Markets:** Over 2.5, Under 2.5, BTTS Yes
- **Primary model:** regularized, time-weighted Dixon–Coles
- **Production eligibility:** deterministic Football league/competition eligibility; H2H is not a Production feature or eligibility gate
- **Decision rule:** configured minimum odds, conservative EV and de-vig probability-edge thresholds
- **Stake rule:** configured fractional Kelly with per-bet, daily, open-risk and drawdown caps

## Production boundary

The current Production model is Dixon–Coles V1. Historical H2H datasets may remain in the repository for research/provenance, but H2H does not enter current Production eligibility, model probability, calibration, EV, edge, market selection or staking.

Production remains paper-only until the operational readiness gate and sufficient timestamp-correct out-of-sample evidence are satisfied.

## Excluded use

- Goals in both halves without a dedicated half-by-half intensity model
- Youth, academy, reserve, B/II and amateur competitions or teams
- In-play betting
- Live staking without validated calibration and separate production authorization

## Material risks

- API coverage and bookmaker mapping vary by competition.
- Sparse league/team history can cause model-fit failures or insufficient training samples.
- Selection effects and market availability can bias observed betting performance.
- Backtest ROI is rejected when odds lack a same-bookmaker ID and a provably pre-decision capture timestamp.
- Parameters can drift across seasons, managers and competition formats.
- Bookmaker limits, rejected stakes and execution delay are not represented by theoretical ROI.
- Calibration validity is necessary but not sufficient evidence of profitability.
- Small out-of-sample samples can produce unstable ROI and CLV estimates.

## Research boundary

Model V2, drift monitoring, signal-strength validation, market-vs-model benchmarking and market-timing research are isolated research activities. They require the explicit research-to-production promotion gate before affecting Production.
