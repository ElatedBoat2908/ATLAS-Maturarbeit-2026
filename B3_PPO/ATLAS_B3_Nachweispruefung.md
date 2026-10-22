# ATLAS – Anhang B3: PPO-Experiment, Nachweispruefung

Pruefdatum: 2026-10-20. Basis: hochgeladenes Originalarchiv `ppo_minimalziel_20261008_v2(1).zip`.

## Pruefumfang

- 20 Originaldateien im ZIP; Integritaet des Archivs und Uebereinstimmung mit den entpackten Dateien geprueft.
- Python-Syntax ist gueltig; Programmcode wurde nachvollzogen. **Kein neues PPO-Training ausgefuehrt.**
- Enthaelt das eingefrorene Experiment-Skript `matura_ppo_minimalziel_frozen_v2.py`, `protocol.json`, `data_audit.json`, drei gespeicherte PPO-Modelle, drei Equity-CSV und PNG, drei Trade-CSV, drei Ergebnis-JSON sowie CSV/JSON der Gesamtuebersicht.
- Ergebnisse unabhaengig aus `fold_n_equity.csv` und `fold_n_trades.csv` nachgerechnet; stimmen exakt (bis auf Rundungsdifferenzen) mit JSON/CSV-Uebersichten ueberein.

## Protokoll und Daten

- Protokollmeldung `frozen_protocol_date = 2026-10-08`, Revision `v2_pre_result_continuity_correction`.
- Urspruengliche M5-Datei `USTEC_M5.parquet`: laut Protokoll 100 000 Zeilen. **Diese Rohdaten sind nicht im ZIP und wurden nicht erneut gehasht/geprueft.**
- Eine auffaellige Quellen-Datenluecke von 55,163 Tagen zwischen 16.07.2025 und 09.09.2025. Algorithmisch ausgewaehltes laengstes zusammenhaengendes Segment 16.09.2024 bis 16.07.2025; 58 327 Zeilen vor Feature-Warm-up, 58 326 danach.
- Merkmale: 20 vollstaendig abgeschlossene M5-Kerzen x 5 Merkmale + aktueller Positionsstatus = 101 Beobachtungswerte. Naechster Open fuer Entscheidung, Open-to-naechstem-Open-Reward, keine Handelskosten.
- Expanding Walk-Forward mit drei getrennten Testabschnitten, keine Weiterschulung im OOS-Test. Die Dateien dokumentieren das Protokoll; aus Dateimetadaten allein laesst sich eine vorherige Fixierung nicht beweissicher belegen.

## Unabhaengig nachgerechnete Ergebnisse

| Fold | Rendite | Winrate | Max. Drawdown | Trades | Angeforderte Trainingsschritte | Modell tatsaechlich |
|---|---:|---:|---:|---:|---:|---:|
| 1 | -11.23 % | 47.99 % | -17.18 % | 2'790 | 64'118 | 65'536 |
| 2 | +9.92 % | 50.13 % | -7.01 % | 1'506 | 81'616 | 81'920 |
| 3 | -3.59 % | 48.50 % | -5.64 % | 4'272 | 99'114 | 100'352 |

**Unterscheidung:** Die Python-Trainingsfunktion ruft Stable-Baselines3 mit 64 118 / 81 616 / 99 114 angeforderten Schritten auf. Da PPO in Bloecken von `n_steps = 2048` trainiert, enthalten die tatsaechlichen Modellarchive 65 536 / 81 920 / 100 352 Schritte. Die Spalte in Tabelle 5 der Arbeit ist als **angeforderte** Schritte korrekt.

## Aus Modellarchiven gelesene Paketversionen

Python 3.12.7; Stable-Baselines3 2.9.0; PyTorch 2.14.1+cpu; NumPy 2.5.1; Gymnasium 1.4.0; Cloudpickle 3.1.2; CPU; Windows 11. Keine Vermutung: die Werte stehen in `system_info.txt` der drei gespeicherten Modellarchive.

## Beurteilung und verbleibende Grenzen

**B3 ist hinsichtlich dokumentierter PPO-Ergebnisse, Trainingsskript, Modelle und Softwareversionen gut belegt.** Die Original-M5-Parquet-Daten fehlen; ihre im Protokoll hinterlegte SHA256-Pruefsumme kann deshalb nicht unabhaengig verifiziert werden. Die bei der Aufnahme der Originaldaten angewendete MT5-Quellenpipeline wurde in dieser Pruefung ebenfalls nicht neu durchlaufen.

**In der Maturaarbeit zu korrigieren:** Die Anhang-B3-Liste nennt bislang `matura_ppo_minimalziel.py`; der tatsaechlich gelieferte eingefrorene Skriptname lautet `matura_ppo_minimalziel_frozen_v2.py`. Den nicht gelieferten Protokoll-Markdown darf man nicht als vorhanden ausweisen. Die aktuelle Abbildung 2 kann durch die drei Equity-CSV-Dateien nachvollzogen werden; sie ist eine nachtraegliche gemeinsame Visualisierung, nicht eine der drei einzel-Fold-PNGs.

**Keine Ueberinterpretation:** Die Testresultate sind OOS-Auswertungen ohne Spread, Slippage und Kommissionen. Sie belegen kein profitables Live-Handelssystem. Der Rohdatenbestand enthaelt laut Protokoll auch 2026, aber der ausgewaehlte PPO-Testabschnitt endet 2025; die 2026-Holdout-Sperre in der Maturaarbeit bezieht sich spezifisch auf die OR5-Untersuchung.


---

**Aktualisierung vom 20.10.2026:** Die bisher fehlende `USTEC_M5.parquet` wurde separat hochgeladen und per SHA-256 exakt mit `protocol.json` und `data_audit.json` abgeglichen. Die nachfolgend/oben beschriebene offene Rohdatenlücke ist hiermit geschlossen. Einzelheiten: `ATLAS_B3_Rohdatenabgleich_2026-10-20.md`. Kein erneutes Training oder Einlesen des Parquet-Inhalts in dieser Prüfung.
