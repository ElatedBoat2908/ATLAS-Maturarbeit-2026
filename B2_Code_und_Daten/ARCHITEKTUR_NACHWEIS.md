# B2: Ergänzende Quellcodeprüfung der ATLAS-Architektur (21.10.2026)

## Prüfgegenstand und Ergebnis

Geprüft wurden **fünf neue Originaluploads**: `command_engine(10).py`, `research_brain(2).py`, `app(2).py`, `agents.zip` und `risk.zip`. Die ZIPs enthalten zusätzlich 9 Python-Dateien unter `agents/` und 5 unter `risk/`; die drei einzeln bereitgestellten `.py`-Dateien ergeben **17 eindeutige Python-Quelldateien** in der ergänzten Architekturstruktur. **Alle 17 Dateien bestanden eine reine Python-Syntaxanalyse (AST)**; es wurde **keine vollständige Anwendung** gestartet.

| Behauptung in Kapitel 3.2 | Vom hochgeladenen Quellcode tatsächlich gestützt | Grenze |
|---|---|---|
| Command Engine leitet Befehle weiter | `command_engine(10).py`: erkennt verschiedene Kommandos und delegiert an `AtlasSupervisor` bzw. `IntelligenceActionController`. | `atlas.application`, `atlas.execution.deployment_guard` und viele Supervisor-Unterfunktionen nicht als vollständige Laufzeitumgebung beigefügt. |
| Brain verarbeitet gespeicherte Markt- und Forschungssignale | `research_brain(2).py`: liest gespeicherte Markteinschätzungen und Dashboards, formuliert deterministische Pläne; zeichnet Begründungen auf. | **Kein Nachweis eines eigenständig lernenden Brain-Modells**. In `_record_cognitive_decision()` sind Confidence-Werte `0.9`/`0.75` und Alternativscores `0.90`/`0.25` fest vorgegeben, keine validierten Wahrscheinlichkeiten. |
| Spezialisierte Agenten | `agents.zip`: Supervisor, MarketAnalyst, StrategyEngineer, QuantValidator, KnowledgeAgent, etc. vorhanden. | Zahlreiche `atlas.*`-Abhängigkeiten dieser Module fehlen im hier untersuchten Zusatzpaket; Orchestrierungsfähigkeit nicht end-to-end getestet. |
| Grafische Benutzeroberfläche | `app(2).py`: Streamlit-Navigation, Chat und Seiten für Markt, Strategien, Forschung, Reporting, Agenten. | `atlas.ui.pages.*`, UI-Komponenten/Theme und `streamlit`-Laufumgebung fehlen im Zusatzpaket. UI wurde **nicht gestartet**. |
| Risiko- und Sicherheitsmodule | `risk.zip`: `AccountRiskEngine`, Prüfungen für Drawdown, Tagesverlust, offene Positionen, Kill-Switch und maximale Positionsrisiken. | Isolierter Smoke-Test: sicherer Kontostand führt zu `ALLOW_NEW_RISK`, Verlustfall zu `BLOCK_NEW_RISK`. Beide Entscheide haben `live_trading_allowed=False`. Keine Prüfung, dass die Engine tatsächlich alle Handelswege des Gesamtsystems sperrt. |

## Herkunft und Version

Originaluploads sind **unverändert** unter `Architektur_Ergaenzung/Originaluploads` enthalten. Unter `Architektur_Ergaenzung/Quelldateien/atlas/...` wurden unveränderte Quelldateien in ihrer vermuteten Projektverzeichnisstruktur zusätzlich einsortiert. Die Suffixe `(10)` und `(2)` stammen aus den hochgeladenen Dateinamen; **sie belegen keinen freigegebenen Commit- oder Versionsstand**. Ein gemeinsamer Code-Snapshot und die damaligen Laufzeitprotokolle fehlen. Es ist daher nicht unabhängig nachgewiesen, dass genau diese Dateistände gleichzeitig zum Zeitpunkt aller in der Maturaarbeit beschriebenen Tests aktiv waren.

## Nicht erforderliche beziehungsweise noch offene Nachweise

Für eine **Beschreibung der modularen Struktur in Kapitel 3.2** reichen die nun vorliegenden Quelldateien als **Codebelege** aus, sofern Formulierungen keine getestete vollständige Funktionsfähigkeit oder echten Live-Handel behaupten.

Eine **ausführbare Reproduktion des vollständigen ATLAS-Systems** bräuchte darüber hinaus unter anderem `atlas/agents`-Abhängigkeiten, `atlas/brain/models.py`, `brain_memory.py`, `atlas/cognitive`, `atlas/application`, `atlas/execution/deployment_guard.py`, UI-Seiten und Komponenten, weitere Runtime-Pakete, Startanleitung und Testprotokolle. Diese sind hier nicht vollständig vorhanden. B3/B4/B5 belegen ihre jeweiligen **separaten** Experimente, nicht eine reibungslose gemeinsame ATLAS-End-to-End-Laufzeit.

## Empfohlener neuer Wortlaut im Word-Dokument: B2

Der digitale Anhang enthält die gesicherten Python-Dateien zur Datenaufbereitung und zu den frühen regelbasierten Backtests, darunter `config.py`, `data_pipeline.py`, `validate_data.py`, `features.py`, `backtest_engine.py` sowie `strategies_v1.py` bis `strategies_v3.py` und zugehörige Ausführungsskripte. Sie dokumentieren den MT5-Datenabruf, die Prüfung und Verarbeitung historischer Kursdaten sowie die frühen Strategieauswertungen. Deren methodische Schwächen sind in Kapitel 4.3 erläutert.

Ergänzend enthält B2 Quellcode zur modularen ATLAS-Architektur: `command_engine(10).py` zur Befehlssteuerung, `research_brain(2).py` zur regelbasierten Forschungsplanung, `agents.zip` mit den spezialisierten Agenten, `app(2).py` zur Streamlit-Benutzeroberfläche sowie `risk.zip` mit Modulen zur Risikoprüfung. Die Dateien belegen die programmierte Struktur dieser Komponenten, nicht jedoch einen vollständigen gemeinsamen Funktionstest oder autonomes Live-Trading. Das PPO-Experiment sowie die Opening-Range-Untersuchungen sind gesondert in den Anhängen B3 bis B5 dokumentiert.

## Integritätsnachweis

Das digitale Paket enthält eine SHA-256-Dateiliste aller enthaltenen Dateien. Die gespeicherten `.py`-Dateien wurden nicht verändert; in der strukturierten Kopie wurden ausschliesslich die Pfade normalisiert. In `agents.zip` und `risk.zip` enthaltene `__pycache__`-Dateien bleiben in den unveränderten Originalarchiven erhalten, sind aber nicht Teil der strukturierten Quelldateisammlung.
