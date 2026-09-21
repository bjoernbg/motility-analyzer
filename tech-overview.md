# Motility Analyzer — Technische Übersicht

## Was macht das Projekt?

Webanwendung zur Analyse von Videoaufnahmen von Darm-Motilitätsexperimenten.

- Verarbeitet Videos **Frame für Frame** (Bild für Bild)
- Findet **Kanten** des Objekts, berechnet eine **Mittellinie** und verteilt **Messpunkte** entlang dieser Linie
- Erzeugt **Heatmaps** der Dicke/Position über Zeit und Ort
- Erkennt automatisch **Kontraktionen** (Wellen) im Heatmap-Verlauf
- Unterstützt das **Vergleichen zweier Analysen** (Heatmap-Differenz, synchrone Wiedergabe)
- Rechnet Pixel in **Millimeter** um (Kalibrierung über Schlauchbreite)

## Grobe Architektur

Das System besteht aus zwei Komponenten, die über HTTP/JSON kommunizieren:

- **Backend (Server):** Macht die ganze Rechenarbeit, hält die Datenbank, liest Videos, liefert Bilder und Ergebnisse aus
- **Frontend (Browser-Oberfläche):** Zeigt Videos, Steuerelemente, Diagramme und Heatmaps an
- **Lokal lauffähig:** Es wird kein Cloud-Dienst benötigt; alles läuft auf einem Rechner
- **REST-API:** Frontend stellt Anfragen an das Backend (z. B. "gib mir Frame Nummer 1234"), Backend antwortet mit Daten oder Bildern

## Backend (Server)

**Sprache & Framework**

- **Python 3.12+** mit **FastAPI** (modernes Python-Web-Framework)
- Paketverwaltung über **uv** (schneller, deterministischer Python-Installer)
- Lint/Format mit **ruff**

**Wichtige Bibliotheken (und wofür)**

- **OpenCV** — Bildverarbeitung: Frames lesen, Glätten, Schwellwerte, Kantenerkennung
- **NumPy / SciPy** — Numerik, lineare Algebra, Gauß-Filter, morphologische Operationen, Connected-Component-Labeling
- **Numba** — Just-in-Time-Kompilierung (beschleunigt rechenintensive Schleifen)
- **python-ffmpeg** + mitgeliefertes **FFmpeg-Binary** (`server/ffmpeg_bin/`) — Video-Re-Encoding nach H.264
- **Brotli-ASGI** — Komprimierung großer API-Antworten (vor allem Heatmap-Daten)
- **WebSockets** — Echtzeit-Updates während laufender Analysen

## Frontend (Web-Oberfläche)

**Sprache & Framework**

- **TypeScript** + **Vue 3** (Composition API mit `<script setup>`)
- **Vite** als Build-Tool (Dev-Server, Type-Check, Produktions-Build)
- **Pinia** für die zentrale Zustands­verwaltung (Videos, Analysen, Einstellungen)

**UI und Visualisierung**

- **TailwindCSS** + **shadcn-vue** / **reka-ui** — Komponenten-Bibliothek und Styling
- **Chart.js** + **vue-chartjs** — Diagramme
- **Three.js** — 3D-Visualisierung (Topographie- / Tube-Ansichten)
- **Canvas-Overlays** — Pfade, Messpunkte und Bereichs­markierungen werden über das Video gezeichnet
- **fflate** — Komprimierung beim Datenexport
- **Vitest** + **Vue Test Utils** für Unit-Tests

## Datenhaltung

- **SQLite-Datenbank** (`server/analyses.db`) im **WAL-Modus** (erlaubt nebenläufige Lese- und Schreibzugriffe)
  - Tabellen: Analysen, Frames, Kontraktions-Ereignisse, kombinierte Analysen
- **Dateibasierte Ablage:**
  - Videos liegen in `server/videos/`
  - Pro Video eine JSON-Datei mit Parametern und Anzeige-Einstellungen
  - Vorberechnete Heatmaps werden als Binärdateien zwischen­gespeichert
- **Mehrstufiges Caching:** Backend (Disk), Frontend (Browser-LRU-Cache, Bild-Cache)

## Wie wird ein Video verarbeitet?

Eine Analyse durchläuft folgende Pipeline:

1. **Upload** des Videos → Speicherung als Datei
2. Bei Bedarf **Re-Encoding** auf H.264 (für Browser-Kompatibilität, via FFmpeg)
3. **Kalibrierung** Pixel ↔ Millimeter anhand der Schlauchbreite (Standard 11 mm)
4. Nutzer setzt Parameter und startet die Analyse
5. Backend verarbeitet das Video **Frame für Frame** in einem Thread-Pool:
   - Kantenerkennung mit der "Silhouette"-Methode (Glätten → Schwellwert → Morphologie)
   - Pfad oben + Pfad unten → Mittellinie → Messpunkt-Paare
   - **Performance** ~90 Frames/Sekunde (abhängig von Anzahl von Messpunkt-Paaren)
1. Ergebnisse werden in **Bündeln** (alle 25 Frames) in die SQLite-Datenbank geschrieben
2. Aus den gespeicherten Messpunkten wird die **Heatmap** erzeugt und auf der Festplatte zwischen­gespeichert
3. Nach Abschluss läuft automatisch die **Kontraktionserkennung** (Glättung → Schwellwert → Regionen → Statistik)

## Besondere Funktionen

- **Combined Analyses:** Zwei abgeschlossene Analysen können kombiniert verglichen werden (Heatmap-Differenz, synchronisierte Wiedergabe)
- **Multi-View-Alignment:** Automatische Zeit- und Bereichs­ausrichtung zweier Kameraansichten
- **Auto-Erkennung** des horizontalen Analysefensters
- **Kalibrierung** auf Schlauchbreite (Standard 11 mm)
- **Frame-Multiplier:** Unterstützt vor-ausgedünnte Videos (jedes n-te Bild im Original)
- **Live-Vorschau** beim Setzen der Analyseparameter (einzelner Frame wird sofort durchgerechnet)

## Datengetriebene Algorithmen / Machine-Learning-nahe Verfahren

Das System setzt überwiegend klassische Bildverarbeitung ein, kombiniert sie aber an mehreren Stellen mit **statistischen und maschinellen Lernverfahren**. Es handelt sich dabei um klassische Machine-Learning- und Signalverarbeitungs­methoden:

- **Lineare Regression (Least-Squares-Fit)** in der Kontraktionserkennung — an jedes erkannte Kontraktions­ereignis wird eine Gerade angepasst; deren Steigung liefert die Ausbreitungs­geschwindigkeit der Welle (`contraction_detection.py`)
- **Kreuzkorrelation zur Signal-Ausrichtung** zwischen zwei Kameraansichten — verschiedene Zeitversätze werden getestet, der mit der höchsten Korrelation gewinnt (`multiview_alignment.py`)
- **Z-Score-Normalisierung** der Signale vor dem Matching — eine Standard-Vorverarbeitung in ML-Pipelines
- **Konfidenz-Scoring:** Vorschläge erhalten einen Konfidenzwert aus Peak-Höhe und -Prominenz; nur Vorschläge oberhalb eines Schwellwerts werden automatisch übernommen
- **Adaptive perzentil­basierte Schwellwerte** — Schwellen werden direkt aus den Daten (Quantile) abgeleitet statt fest vorgegeben (sowohl bei der Kontraktions­erkennung als auch bei der Tube-Anker-Detektion)
- **Connected-Component-Labeling** — unsupervised Segmentierung der Heatmap in zusammenhängende Kontraktions­regionen, anschließend Filterung nach Größen­merkmalen wie Pixelzahl, Fläche und Höhe
- **Median-Aggregation über mehrere Stichproben** als robuste, gegen Ausreißer resistente Statistik

## Technische Optimierungen

- **Frame-für-Frame-JPEG-Auslieferung** statt klassischem Video-Streaming → ermöglicht exakte, reproduzierbare Bildauswahl
- **Video-Handle-Pool** (LRU, max. 5 offene Dateien, 60 s Idle-Timeout) → schnelles Springen zu beliebigen Frames ohne Datei jedes Mal neu zu öffnen
- **Brotli-Kompression** für API-Antworten ab 500 Byte (mit GZip-Fallback)
- **Request-Cancellation** im Frontend (`AbortController`) verhindert veraltete Antworten bei schnell wechselnden Benutzer­aktionen
- **Hintergrund-Tasks** mit ThreadPoolExecutor (Workerzahl ≈ CPU-Kerne − 1)
- **Persistierung in Bündeln** (alle 25 Frames) statt nach jedem Frame → weniger Datenbank-Last
- **Frontend-Heatmap-Cache** auf Sessions-Ebene (LRU, max. 10 Analysen)

## Größe & Entwicklung

- **Server:** ca. 19 Python-Module in einer monolithischen FastAPI-App (`server/`)
- **Client:** ca. 50+ Vue-Komponenten (`client/src/components/`)
- **Tests:** pytest im Server, **Vitest** im Client
- **Code-Qualität:** `ruff` für Python, `prettier` und `vue-tsc` (Type-Check) für das Frontend
-
