# QuantBet H2H v2

Launch-ready **paper-trading** architecture for football market screening.

The public GitHub Pages dashboard is Football-only and is organized into five first-class sectors: Overview, Production, Strong Signals, Near Misses and History.

Production is the only accounting surface. Strong Signals and Near Misses are observational/analytical surfaces and never alter Production bank, P/L, ROI or settlement.

The dashboard uses one shared presentation design system and canonical lifecycle data. Missing Opening/Pick/Closing observations remain explicitly unavailable; the UI never fabricates prices, timestamps, bookmakers or CLV.

Kickoff times are displayed in `Europe/Belgrade` / Serbian local time.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the mathematical contract.
