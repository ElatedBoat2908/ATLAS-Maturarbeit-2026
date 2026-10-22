# ATLAS – B3: Abgleich der Originaldaten `USTEC_M5.parquet`

Prüfdatum: 20. Oktober 2026. Grundlage: einzeln hochgeladene `USTEC_M5.parquet` und das zuvor geprüfte Original-PPO-Archiv `ppo_minimalziel_20261008_v2(1).zip`.

## Ergebnis der Integritätsprüfung

| Prüfung | Feststellung |
|---|---|
| Quelldatei | `USTEC_M5.parquet` |
| Dateigrösse | 2,668,737 Bytes |
| SHA-256 (hochgeladene Datei) | `4edc1117beb9f38badc3cdf028318b36b3144bef3af594932d37cf76c9b636c7` |
| SHA-256 in `protocol.json` | `4edc1117beb9f38badc3cdf028318b36b3144bef3af594932d37cf76c9b636c7` |
| SHA-256 in `data_audit.json` | `4edc1117beb9f38badc3cdf028318b36b3144bef3af594932d37cf76c9b636c7` |
| Ergebnis | **Exakt gleiche Prüfsumme. Die Datei ist dem eingefrorenen PPO-Protokoll eindeutig zugeordnet.** |
| Dateiformat | Parquet-Kopf- und Endkennung `PAR1` vorhanden |

Die starke Hash-Übereinstimmung bestätigt die Identität der hochgeladenen Datei mit den im Protokoll referenzierten Dateibytes; das ist keine nachträglich veränderte oder rekonstruierte Datendatei.

## Bereits dokumentierter Inhalt laut `data_audit.json` / `protocol.json`

- Ursprünglicher Datensatz: **100'000 M5-Zeilen**, von 16.09.2024 12:15 UTC bis 15.04.2026 19:45 UTC.
- Einzige protokollierte Datenlücke über 7 Tage: zwischen 16.07.2025 10:40 UTC und 09.09.2025 14:35 UTC (**55,1632 Tage**).
- Vor Auswertung festgelegte Segmentregel laut Protokoll: längstes zusammenhängendes Segment nach Zeilenzahl wählen (bei Gleichstand das frühere).
- Ausgewähltes Segment: **58'327 M5-Zeilen**, 16.09.2024 bis 16.07.2025; nach Merkmalsaufbereitung **58'326 Zeilen**.
- Die drei OOS-Testzeiträume, Modellparameter und Ergebniskennzahlen sind in der vorherigen B3-Prüfung separat durch CSV-Dateien nachgerechnet worden.

**Grenze dieser Nachprüfung:** Da die technische Umgebung keinen installierten Parquet-Leser enthält, wurden die Datenzeilen der Datei bei diesem Upload nicht nochmals unabhängig eingelesen oder die gesamte Trainingspipeline ausgeführt. Ihre Byteidentität zum bereits geprüften Protokoll ist jedoch per SHA-256 verifiziert. Die hier genannten Zeilenzahlen und Zeitgrenzen stammen daher aus den archivierten Originalprotokollen; sie sind nicht aus einer unabhängigen neuen Parquet-Auswertung abgeleitet.

## Verwendung in der Maturaarbeit

Die Darstellung in Kapitel 4.1 und 4.4 zur PPO-Datenlücke und zum ausgewählten Zeitraum wird von den Originalprotokollen gestützt. Die drei Fold-Zahlen und Trainingsschritte aus Kapitel 4.4 und 5.2 bleiben unverändert. Im digitalen Anhang B3 ist `USTEC_M5.parquet` nun zusätzlich enthalten.

**B3-Status:** Original-PPO-Code, Modelle, Trade-/Equity-Ergebnisse, Protokolle, Original-M5-Datendatei und SHA-256-Prüfprotokoll vorhanden. Vollständige Reproduzierbarkeit durch erneutes Training und MT5-Rohdatenexport bleibt ein gesonderter Schritt; hier wurde kein neues Training behauptet.
