# QuantBet Forensic Reset — 2026-09-10

## Conclusion

The Dixon–Coles model/market/risk layer is reusable. The recurring failures are in orchestration, state ownership and public projection. The system was allowing multiple layers to write or reinterpret the same Strong/Near evidence.

## Root causes confirmed

1. **Strong/Near producer split.** `main.py generate` persisted intraday Strong Signals while `watchlist.yml` was documented as the sole scheduled producer. This violated the canonical-writer contract and created competing semantics.
2. **Public Near Miss duplication.** `tools/build_public_signal_buckets.py` projected individual legacy observations even when a canonical lifecycle already represented the same observation group. This could place a malformed legacy row before the canonical row and expose null identity on the dashboard.
3. **Fixture identity loss at observation creation.** `market_timing.build_snapshot()` persisted fixture/market/odds metadata but omitted `home_name`, `away_name` and `match`. That made downstream public reconstruction dependent on later inference instead of carrying authoritative identity with the observation.
4. **Public validation was too weak.** The dashboard validator accepted `near_misses.json` with missing canonical identity and did not enforce the Near Miss lifecycle schema. A green Pages build therefore did not mean a usable Near Miss surface.
5. **CI was not green.** Before this reset, run 800 had 198 passing tests and one failing Near Miss public-projection regression. The failure was consistent with the duplicate legacy projection described above.

## Structural changes applied

- `watchlist.yml` remains the sole scheduled Strong/Near producer; the `main.py generate` Strong persistence hook is now a compatibility no-op.
- Public Near Miss projection now excludes every source observation already represented by a canonical lifecycle row, not only the latest observation ID.
- Market-timing observations now carry authoritative fixture identity into both timing and canonical odds snapshots.
- Public dashboard validation now fails closed on missing Near Miss identity/lifecycle fields.
- Added regression coverage for fixture identity in market-timing snapshots.

## What is intentionally NOT declared complete

- Real scheduled runtime proof for #138/#140/#114/#117 is still required.
- #78 global quota still needs production-run evidence, not only implementation evidence.
- #59 remains open until the full operational audit passes.
- No model, calibration, EV/edge, Kelly/risk or eligibility mathematics were changed.

## Operating rule from here

Do not add another feature patch to Production until the canonical state path is green:

`provider fixture → prediction identity → observation → classification → canonical lifecycle → settlement → public projection → dashboard validation`

A failure at any stage must be visible as ERROR/BLOCKED rather than represented as an empty/healthy dashboard.
