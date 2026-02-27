# Wochenplan-Freigabe -- Review Sheet Spec

## Zweck

Der Betriebsleiter prueft den wochentlichen Besetzungsplan bevor die Schichten
in Ordio bestaetigt werden. Dieses Dokument definiert das Format des
Freigabe-Blattes: eine durchsuchbare Tabelle mit Empfehlungen, Begruendungen
und Entscheidungsfunktion.

Das Review Sheet ist das zentrale Entscheidungsdokument im Freigabeprozess.

---

## Kopfbereich

### Metadaten

```
+------------------------------------------------------------------+
|  Betrieb: Hin&Weg           Plan: plan-8e4456803f41              |
|  Zeitraum: 23.02. - 01.03.2026    Profil: hinweg_march_2026     |
+------------------------------------------------------------------+
```

### KPI-Leiste

| Kennzahl | Wert | Beschreibung |
|----------|------|-------------|
| Besetzungsrate | 100% | Zugewiesene / Gesamt offene Schichten |
| Zugewiesen | 7 | Schichten mit Empfehlung |
| Offen | 0 | Schichten ohne Empfehlung |
| Davon Bewerbungen | 2 | Zuweisungen basierend auf Bewerbung |
| Davon Empfehlungen | 5 | Zuweisungen ohne Bewerbung |

### Entscheidungs-Zusammenfassung

```
  [ 7 Ausstehend ]   [ 0 Angenommen ]   [ 0 Abgelehnt ]

  [ Alle annehmen ]   [ Zuruecksetzen ]
```

---

## Wochenplan-Tabelle

Die Haupttabelle zeigt alle Schichtzuweisungen, gruppiert nach Tag.

### Spalten

| # | Spalte | Inhalt | Breite |
|---|--------|--------|--------|
| 1 | **Tag** | Wochentag + Datum, z.B. "Mo 23.02." | 100px |
| 2 | **Schicht** | Uhrzeit + Typ-Badge | 130px |
| 3 | **Bereich** | Arbeitsbereich | 130px |
| 4 | **Empfehlung** | Mitarbeitername (fett wenn Bewerber) | 180px |
| 5 | **Bewerbung** | Ja/Nein Badge | 70px |
| 6 | **Score** | Gesamtpunktzahl, farbcodiert | 60px |
| 7 | **Begruendung** | 2-3 Zeilen Erklaerungstext | flex |
| 8 | **Alternativen** | Aufklappbar, Top 3 | 60px |
| 9 | **Entscheidung** | Annehmen / Ablehnen Buttons | 140px |

### Farbcodierung Score

| Bereich | Farbe | Bedeutung |
|---------|-------|-----------|
| >= 100 | Gruen | Starke Empfehlung (meist mit Bewerbung) |
| >= 80 | Gelb | Solide Empfehlung |
| < 80 | Rot | Schwache Empfehlung, Alternativen pruefen |

### Tagesgruppierung

Tage werden visuell getrennt. Innerhalb eines Tages sortiert nach Startzeit.

```
+--------+----------------+---------+-------------------+-----+-------+
| Tag    | Schicht        | Bereich | Empfehlung        | Bew | Score |
+--------+----------------+---------+-------------------+-----+-------+
|        |                |         |                   |     |       |
| Mo     | 10:00-13:00    | Kiosk   | **R.Y. Morsi**    | Ja  |  144  |
| 23.02. | frueh          |         |                   |     |       |
|--------+----------------+---------+-------------------+-----+-------|
|        |                |         |                   |     |       |
| Di     | 06:45-14:45    | Kiosk   | Annika Geyer      | --  |   92  |
| 24.02. | frueh          |         |                   |     |       |
|--------+----------------+---------+-------------------+-----+-------|
|        |                |         |                   |     |       |
| Fr     | 10:00-14:00    | Prod.   | Marco Hiller      | --  |   92  |
| 27.02. | frueh          |         |                   |     |       |
|        +----------------+---------+-------------------+-----+-------|
|        | 15:00-22:30    | Kiosk   | Carlo Sohn        | --  |   92  |
|        | spaet          |         |                   |     |       |
+--------+----------------+---------+-------------------+-----+-------+
```

---

## Begruendungs-Spalte

Die Begruendung erklaert in Klartext, warum dieser Mitarbeiter empfohlen wird.
Alle Texte auf Deutsch.

### Format fuer Bewerbungen

```
Bewerbung eingegangen. Bewerber-Bonus: +80 Punkte.
Restkapazitaet: {remaining}h von {target}h Monatsziel.
Fairness: {fairness}/30. Skills: {area}-Match ({skill_score}).
```

Konkretes Beispiel (Raphael, Mo 23.02.):
```
Bewerbung eingegangen. Bewerber-Bonus: +80 Punkte.
Restkapazitaet: 24h von 40h Monatsziel. Fairness: 18/30.
Skills: Kiosk-Match (12). Rollenfit: 10. Gesamt: 144.
```

### Format fuer Empfehlungen (ohne Bewerbung)

```
Empfehlung: {primary_reason}.
Fairness: {fairness}/30 ({week_shifts} Schichten diese Woche).
Skills: {area}-Match. Geprueft: {constraints_checked}.
```

Konkretes Beispiel (Annika, Di 24.02.):
```
Empfehlung: Hoechste Restkapazitaet (34.6h von 34.6h Ziel).
Fairness: 30/30 (0 Schichten diese Woche). Skills: Kiosk-Match.
Geprueft: Ruhezeit OK, Monatsgrenze OK, kein Ueberstundenrisiko.
```

### Begruendungs-Bausteine

| Baustein | Bedingung | Text |
|----------|-----------|------|
| Bewerbung | is_applicant = true | "Bewerbung eingegangen. Bewerber-Bonus: +80." |
| Restkapazitaet | rest > 0 | "Restkapazitaet: {remaining}h von {target}h Ziel." |
| Fairness | fairness > 0 | "Fairness: {score}/30 ({n} Schichten diese Woche)." |
| Skills | skill > 0 | "Skills: {area}-Match ({score})." |
| Rollenfit | role > 0 | "Rollenfit: {score}." |
| Festes Muster | fixed > 0 | "Regelmaessige Schicht (historisches Muster)." |
| Praeferenz | preference > 0 | "Passt zu Schichtpraeferenz." |
| Gehaltswarnung | salary < 0 | "Hinweis: Nahe an Gehaltsgrenze (-12)." |
| Geprueft | always | "Geprueft: Ruhezeit OK, Monatsgrenze OK." |

---

## Alternativen (aufklappbar)

Klick auf eine Zeile zeigt die Top-3-Alternativkandidaten:

| # | Alternativkandidat | Score | Delta | Gruende | Blockiert? |
|---|-------------------|-------|-------|---------|------------|
| 1 | Annika Geyer | 92 | -52 | Restkapazitaet, Fairness, Skill-Match | -- |
| 2 | Carlo Sohn | 92 | -52 | Restkapazitaet, Fairness, Skill-Match | -- |
| 3 | Ece Genca | 92 | -52 | Restkapazitaet, Fairness, Skill-Match | -- |

**Delta** = Score Alternative - Score Empfehlung. Negativ = Empfehlung ist besser.

Wenn ein Alternativkandidat blockiert ist:
```
| 4 | Elena Schroeder | -- | -- | -- | Keine Zusatzschichten |
```

---

## Nicht besetzte Schichten

Falls Schichten nicht besetzt werden konnten, erscheint eine separate Tabelle:

| Tag | Schicht | Bereich | Grund | Top-Kandidaten (blockiert) |
|-----|---------|---------|-------|---------------------------|
| Mi 26.02. | 10:00-16:00 | Produktion | Alle blockiert | Elena (no_additional), Luise (no_additional), Jana (max_weekly) |

### Gruende fuer Nicht-Besetzung

| Grund-Code | Erklaerung |
|------------|-----------|
| `no_valid_candidate` | Kein Kandidat erfuellt alle Bedingungen |
| `no_candidates_available` | Keine Mitarbeiter im System |
| `all_candidates_blocked_by_constraints` | Alle durch Einschraenkungen gesperrt |
| `all_applicants_blocked` | Bewerber vorhanden, aber alle gesperrt |

---

## Entscheidungs-Workflow

### Aktionen pro Zeile

| Button | Farbe | Aktion |
|--------|-------|--------|
| **Annehmen** | Gruen | Setzt Status auf "angenommen" |
| **Ablehnen** | Rot | Setzt Status auf "abgelehnt" |

### Sammelaktionen

| Button | Aktion |
|--------|--------|
| **Alle annehmen** | Setzt alle "ausstehend" auf "angenommen" |
| **Zuruecksetzen** | Setzt alles auf "ausstehend" zurueck |

### Wichtig

- Entscheidungen sind **nur lokal** gespeichert (localStorage im Browser)
- Es erfolgt **kein Rueckschreiben** nach Ordio
- Das Sheet dient als Freigabe-Dokument: nach Pruefung werden die Schichten
  manuell in Ordio bestaetigt
- Bei Ablehnung: Alternative aus der Aufklappliste waehlen und manuell eintragen

---

## Filter und Suche

| Filter | Optionen | Funktion |
|--------|----------|----------|
| Textsuche | Freitext | Filtert nach Mitarbeitername, Bereich, Datum |
| Schichttyp | Alle / Frueh / Spaet | Blendet nach Typ ein/aus |
| Status | Alle / Ausstehend / Angenommen / Abgelehnt | Zeigt nur gewaehlten Status |

Filter kombinieren sich mit UND-Logik.

---

## Datenvertrag

Das Review Sheet konsumiert zwei statische JSON-Dateien:

| Datei | Pfad | Inhalt |
|-------|------|--------|
| `plan.json` | `public/data/plan.json` | Zuweisungen mit Score, Begruendung, Alternativen |
| `snapshot.json` | `public/data/snapshot.json` | KPIs, offene Schichten, Bewerbungen |

Beide werden durch den ordio-lite MCP generiert und als Fixtures committed.
Keine Live-API-Aufrufe aus dem Frontend.
