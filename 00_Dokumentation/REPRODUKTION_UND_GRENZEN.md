# Prüfung, Datenrechte und wissenschaftliche Grenzen

- **Dateiintegrität:** `pruefe_dateien.py` prüft SHA-256-Hashes der enthaltenen Dateien, nicht die wissenschaftliche Richtigkeit der Methoden.
- **B2 Code:** frühe Strategien haben dokumentierte methodische Fehler; spätere Architektur enthält fehlende Python-Importmodule (unter anderem `atlas.application`, `atlas.execution` und UI-Seiten). Gesamtes ATLAS-System ist nicht nachweislich direkt startfähig.
- **B3 PPO:** Originalmodell und Ergebnisse, aber kein neuer kompletter Trainingslauf. Broker-Rohdaten und die detaillierten Preis-/Trade-Dateien sind hier zurückgehalten. Reward im Python-Code: relativer Open-to-Open-Ertrag in der gewählten Position, ohne Transaktionskosten.
- **B4/B5:** Vorhandene Manifeste und Protokolle erlauben Quelleneinsicht; die preisbezogenen JSONL-Einzelereignisse bzw. Einzeltrades bleiben vor Klärung der Datenrechte in der Schulfassung. Die historischen M1-Rohdaten sowie einige Laufzeitabhängigkeiten fehlen ohnehin für eine unabhängige Neu-Ausführung.
- **B6:** Alte Parquet-Trades/Equity-Dateien in Schulfassung; sie eignen sich wegen Look-ahead- und Ausführungsproblemen nicht als Beleg einer profitablen Strategie.
- **B7:** Kein vollständiger unabhängiger Handelsauszug der persönlichen simulierten FTMO-Phase verfügbar.

Dies ist eine eingeschränkte Einsichtsfassung. **Ein vollständiger Replikationsnachweis liegt nicht vor.**
