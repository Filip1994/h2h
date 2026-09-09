import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGES = [
    "index.html",
    "production.html",
    "strong-signals.html",
    "near-misses.html",
    "history.html",
]