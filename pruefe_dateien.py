#!/usr/bin/env python3
"""ATLAS: verifies only package SHA-256 integrity; does not execute backtests."""
from pathlib import Path
import csv
import hashlib
import sys

root = Path(__file__).resolve().parent
manifest = root / "DATEIMANIFEST_SHA256.csv"
if not manifest.is_file():
    sys.exit("FEHLER: DATEIMANIFEST_SHA256.csv nicht gefunden")
errors = []
with manifest.open(encoding="utf-8-sig", newline="") as fp:
    rows = list(csv.DictReader(fp))
for row in rows:
    p = root / row["datei"]
    if not p.is_file():
        errors.append("Fehlt: " + row["datei"])
        continue
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if digest != row["sha256"]:
        errors.append("Unstimmig: " + row["datei"])
print(f"Geprueft: {len(rows)} Dateien")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print("OK: alle gelisteten Dateien stimmen mit dem Paketmanifest ueberein.")
print("Hinweis: Hashabgleich allein validiert keine Handelssimulation.")
