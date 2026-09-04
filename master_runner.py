"""Backwards-compatible daily entrypoint."""

from main import run_generate

if __name__ == "__main__":
    raise SystemExit(run_generate(deliver_email=True))
