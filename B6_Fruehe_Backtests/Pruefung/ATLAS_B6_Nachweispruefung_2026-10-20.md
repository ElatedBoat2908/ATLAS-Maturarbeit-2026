# Anhang B6 – Unabhängige Prüfung der frühen ATLAS-Backtests

Stand: 20. Oktober 2026. Die sechs vom Verfasser bereitgestellten historischen Parquet-Dateien wurden direkt geöffnet. Kennzahlen wurden aus den Trade- und Equity-Werten neu berechnet, ohne das ursprüngliche Signalexperiment neu zu starten. Die Kontrollrechnungen entsprechen der Logik `summarize_results` im beigefügten `backtest_engine.py`.

| Strategie | Anzahl Trades | Winrate | Durchschnitt in R | Profit Factor | Maximaler Drawdown | Startkapital USD |
|---|---:|---:|---:|---:|---:|---:|
| Trend-Pullback V1 | 572 | 39.1608 % | +0.174825 R | 1.285448 | -7.104895 % | 10,000 |
| Trend-Pullback V3 | 563 | 39.4316 % | +0.182948 R | 1.281840 | -6.419516 % | 100,000 |
| v3_exp_001_no_hour_9 | 520 | 40.3846 % | +0.211538 R | 1.339294 | -6.847392 % | 100,000 |

## Kritischer Abgleich mit der Maturaarbeit

1. **Tabelle 7 stimmt.** Tradeanzahl, Winrate, durchschnittliches R, Profit Factor und Drawdown stimmen gerundet mit den originalen Parquet-Auswertungen überein.
2. **Kapitel 4.2 zum Startkapital muss differenziert werden.** V1 startete gemäss gespeichertem Equity-Verlauf mit 10'000 USD, V3 und `v3_exp_001_no_hour_9` hingegen mit 100'000 USD. Die vorliegende `config.py` setzt 10'000 USD als Default und die `run_v3.py` verwendet diesen Default; folglich genügt der aktuell zugeordnete Code nicht, um den V3-Historienlauf mit 100'000 USD exakt zu rekonstruieren. Vermutlich lag eine andere Konfiguration/Codeversion vor; dies ist eine Hypothese und kein geprüfter Sachverhalt. Der Unterschied muss im Text genannt werden.
3. **Die historischen Resultate sind wissenschaftlich nicht belastbar.** `features.py` markiert Swing-Punkte erst anhand von 3 späteren Kerzen, trägt sie aber am früheren Zeitpunkt ein. `backtest_engine.py` kann zu einem Kerzenschlusskurs einsteigen, aus dem das Signal bereits ermittelt wurde. Diese zwei Schwächen sind unabhängig von der korrekten arithmetischen Auswertung der gespeicherten Trades.
4. **Das Rohsignal- und Rohdatenexperiment wurde nicht erneut ausgeführt.** Die Parquet-Dateien belegen archivierte Trades/Equity, nicht einen vollständigen, aus Rohdaten wiederholten Backtest. Die vollständige historisch verwendete Konfiguration und eine separate datierte Experimentdokumentation wurden derzeit nicht eindeutig zugeordnet. Für `v3_exp_001_no_hour_9` ist in den hier zugeordneten B2-Dateien kein nachweislich damals ausgeführtes spezielles Runner-Skript belegt.
5. **Equity-Verläufe haben je 99'999 Zeilen.** Dies ist nicht mit der Anzahl abgeschlossener Trades zu verwechseln. Die verifizierten Spalten und Parquet-Metadaten liegen in den Originaldateien vor.

## Empfohlene Textkorrektur Kapitel 4.2

Bisher: "Als Startkapital legte ich 10'000 USD fest."

Neu: "Das in den gesicherten Backtest-Ergebnissen verwendete Startkapital betrug bei V1 10'000 USD und bei den beiden V3-Varianten 100'000 USD. Für den Vergleich der Strategien verwendete ich deshalb vor allem relative Kennzahlen wie Winrate, durchschnittliches Ergebnis in R, Profit Factor und maximalen Drawdown."

Die gespeicherten Kapitalbeträge zeigen **nicht**, dass alle zugrunde liegenden Modelle unter identischen Handelskosten und genau gleich kalibrierten Positionsgrössen liefen.

## Vorschlag für B6

Der digitale Anhang enthält die originalen Einzeltrade- und Equity-Auswertungen der frühen regelbasierten Backtests: `v1_trades.parquet`, `v1_equity.parquet`, `v3_trades.parquet`, `v3_equity.parquet`, `v3_exp_001_no_hour_9_trades.parquet` und `v3_exp_001_no_hour_9_equity.parquet`. Die daraus erneut berechneten Kennzahlen stimmen mit Tabelle 7 überein. Die archivierten Equity-Dateien weisen bei V1 10'000 USD und bei den beiden V3-Varianten 100'000 USD Startkapital aus. Die historischen Ergebnisse sind wegen der in Kapitel 4.3 beschriebenen methodischen Schwächen nicht als Nachweis profitabler Strategien geeignet. Ein vollständiger Neulauf anhand der ursprünglichen Rohdaten sowie eine eindeutige Zuordnung der damaligen Experimentkonfiguration wurden nicht durchgeführt.

## Prüfmethode

Die Parquet-Dateien wurden durch direkten Thrift/Parquet-Seitenzugriff mit Snappy-Dekomprimierung gelesen, die jeweils aufgezeichneten `pnl_cash`-, `r_multiple`- und `equity`-Spalten unabhängig aggregiert. Der Python-Code `backtest_engine.py` diente dem Abgleich der Kennzahlendefinitionen; er wurde nicht erneut mit ursprünglichen Signaldaten ausgeführt. Die Dateiprüfsummen sind separat dokumentiert.
