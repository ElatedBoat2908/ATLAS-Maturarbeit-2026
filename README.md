# ATLAS – Digitaler Anhang (GitHub-Prüfversion)

**Fassung 22. Oktober 2026 · Noch NICHT öffentlich freigegeben**

Zu der Maturaarbeit «Kann KI besser traden als ein Mensch? Eine kritische Untersuchung mit ATLAS und meiner eigenen Tradingstrategie am Nasdaq-100».

Dieses Repository ist als **lesbarer digitaler Anhang** vorbereitet. Es enthält eine Auswahl von Quellcode, Versuchsprotokollen und zusammenfassenden Ergebnissen. Einige Quellen sind aus Datenschutz- oder möglichen Lizenzgründen **nur in der vollständigeren Schulversion enthalten**. Bis diese Fragen geklärt sind, ist auch diese Ausgabe eine **Prüfversion**, keine Freigabe zur Veröffentlichung.

## Wo finde ich was?

| Abschnitt | Zweck und Link | Einschränkung |
|---|---|---|
| [B1 – Projektvertrag](B1_Projektvertrag/) | Hinweise zum ursprünglichen Forschungsauftrag | Unterschriebener Vertrag nur in der Schulfassung |
| [B2 – Quellcode](B2_Code_und_Daten/) | [Frühe Python-Skripte](B2_Code_und_Daten/fruehe_entwicklung/) und [ATLAS-Architektur](B2_Code_und_Daten/architektur/atlas/) | Gesamtanwendung nicht unabhängig startfähig nachgewiesen |
| [B3 – PPO](B3_PPO/) | PPO-Skript, Trainingskonfiguration, 3-Fold-Kennzahlen, Equity und Modelle | Ursprüngliche M5-Broker-Rohdaten und Einzeltrade-CSV in Schulfassung |
| [B4 – Opening Range](B4_OR5_Marktmuster/) | Ereignis-/Phasen-Manifeste und Auswertungscode | Preisbezogene JSONL-Einzelereignisse in Schulfassung |
| [B5 – Ausführbare OR5](B5_OR5_Trades/) | Kostenkalibrierung, Strategieprotokolle und Prüfscripts | Einzeltrades mit Kursdaten in Schulfassung |
| [B6 – frühe Backtests](B6_Fruehe_Backtests/) | Historische Prüfberichte und Kennzahlenabgleich | Preisbezogene Parquet-Originale in Schulfassung; Fehler in ursprünglicher Backtestlogik |
| [B7 – Eigene Strategie](B7_Eigene_Strategie/) | Grenzen der persönlichen FTMO-Angaben | Kein vollständiger unabhängiger Trade-Auszug vorhanden |

## Resultate

- PPO: drei Walk-Forward-Folds mit −11,23 %, +9,92 %, −3,59 %. Keine stabile Profitabilität belegt; Kosten nicht enthalten.
- Opening Range OR5: 988 Development-, 502 Validation- und 249 Confirmation-Fälle, Musterfortsetzung häufiger als Gegenbewegung.
- Ausführbarer OR5-Tradetest: 1'364 simulierte Trades, −0,27 R durchschnittlich und Profit Factor rund 0,39. Ansatz wurde verworfen.
- Eigene Strategie: nur persönliche, nicht unabhängig überprüfte Angaben; kein direkter fairer Mensch-KI-Vergleich möglich.

## Technik und Nachprüfbarkeit

- `.py`, `.json`, `.csv` und `.md` lassen sich direkt in der GitHub-Weboberfläche ansehen.
- Die gespeicherten `.zip`-PPO-Modelle müssen zur weiteren Untersuchung heruntergeladen werden.
- Die Quellcodes dienen zur Einsicht; für die gesamte Anwendung fehlen weitere Laufzeitmodule. Die hier bereitgestellten Originalprogramme dürfen nicht ohne Prüfung an ein echtes Tradingkonto angeschlossen werden.
- Mit `python pruefe_dateien.py` lassen sich SHA-256-Prüfsummen des hier zusammengestellten Pakets kontrollieren. Das ist **keine unabhängige Neuberechnung sämtlicher Experimente**.
- Siehe [Dokumentierte Grenzen](00_Dokumentation/REPRODUKTION_UND_GRENZEN.md).

**Die vollständigere Schulfassung darf NICHT als öffentliches Repository hochgeladen werden**, weil sie unter anderem einen unterschriebenen Projektvertrag sowie historische Brokerdaten enthält.
