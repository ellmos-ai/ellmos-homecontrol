# Sicherheitsrichtlinie / Security Policy

## Deutsch

### Unterstützte Versionen

| Version | Unterstützt |
| --- | --- |
| `0.1.x` | Ja |

### Sicherheitslücken melden

Wenn Sie eine Sicherheitslücke finden, melden Sie diese bitte verantwortungsvoll:

1. **Kein öffentliches Issue eröffnen**
2. **GitHub Private Vulnerability Reporting verwenden:**
   Öffnen Sie im Repository `Security` → `Advisories` → `New` und reichen Sie die Meldung privat ein.
3. Geben Sie Beschreibung, Reproduktionsschritte, betroffene Komponenten und potenzielle Auswirkungen an.

Falls Private Vulnerability Reporting im Repository nicht verfügbar sein sollte, kontaktieren Sie die Maintainer direkt über GitHub, ohne Details öffentlich zu posten.

### Geltungsbereich

- **TR-064 / SOAP-Hilfsfunktionen:** `FritzBoxAdapter.tr064_call` (XML-Escaping, Tag-Validierung, HTTP-Timeout)
- **Sicherheits-Gates:** `HomeControlHub` Berechtigungs-Gate (`smarthome_permission`) und Bestätigungs-Gate (`HighLoadConfirmationRequiredError`)
- **CLI-Eingaben:** `ellmos_homecontrol.cli` JSON-Parsing und Befehlsausführung

### Reaktionszeit

Wir bestätigen Meldungen in der Regel innerhalb von **48 Stunden**, bewerten den Schweregrad innerhalb von **5 Tagen** und koordinieren Behebungen zeitnah vor einer öffentlichen Bekanntgabe.

---

## English

### Supported Versions

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes |

### Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not open a public issue**
2. **Use GitHub Private Vulnerability Reporting:**
   Open `Security` → `Advisories` → `New` in the repository and submit the report privately.
3. Include a description, reproduction steps, affected components, and potential impact.

If private vulnerability reporting is not enabled on the repository, contact the maintainers directly via GitHub without disclosing details publicly.

### Scope

- **TR-064 / SOAP Helpers:** `FritzBoxAdapter.tr064_call` (XML escaping, tag validation, HTTP timeout)
- **Safety Gates:** `HomeControlHub` permission gate (`smarthome_permission`) and high-load confirmation gate (`HighLoadConfirmationRequiredError`)
- **CLI Inputs:** `ellmos_homecontrol.cli` JSON parsing and command dispatch

### Response Time

We aim to acknowledge reports within **48 hours**, triage severity within **5 days**, and coordinate fixes before public disclosure.
