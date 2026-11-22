# Changelog / Änderungsprotokoll

Alle wesentlichen Änderungen an diesem Projekt werden hier dokumentiert.
Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Hinzugefügt / Added
- GitHub Actions CI-Matrix (`.github/workflows/ci.yml`) für `ubuntu-latest`, `windows-latest` und `macos-latest` über Python 3.10–3.13 inkl. `pip check`, `compileall`, `ruff` und `pytest`.
- Dependabot-Konfiguration (`.github/dependabot.yml`), Standard-Labels (`.github/labels.yml`), PR-Workflows (`auto-assign.yml`, `label-sync.yml`, `stale.yml`) und zweisprachige Issue-Templates (`.github/ISSUE_TEMPLATE/`).
- Community- und Sicherheitsdokumentation (`CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`), `MANIFEST.in` und PEP-561-Marker (`src/ellmos_homecontrol/py.typed`).
- Vertragstest-Suite (`tests/test_metadata.py`) für PEP-621/639-Metadaten, `.gitignore`-Schutzregeln, CI-Integrität, `ellmos-module.v2.json`-Parität, README-Konsistenz und CLI-Kommandos.

### Geändert / Changed
- `pyproject.toml` um PEP-621-URLs, Keywords, Classifiers, `license-files`, `ruff`-Konfiguration und `pytest`-`norecursedirs`/`xfail_strict` (ohne relatives `--basetemp`) erweitert.
- `.gitignore` gegen Multi-Agent-Locks, Cloud-Sync-Konfliktkopien, lokale Caches und `.pytest_temp/` gehärtet.
- Redundanten lokalen `import re` in `FritzBoxAdapter.xml_value` entfernt.
- `README.md` und `README_de.md` auf aktuellen Testpfad (`tests/`), `dev`-Abhängigkeiten und Community-Dokumente abgestimmt.

## [0.1.0] - 2026-11-06

### Hinzugefügt / Added
- Erstveröffentlichung von `ellmos-homecontrol` mit `HomeControlHub`, `HomeDevice`, Bestätigungs-Gate für Hochlast-/sicherheitskritische Geräte, `FritzBoxAdapter` (TR-064 SOAP mit XML-Escaping), Adapter-Konfigurationsklassen (`HomeAssistantAdapter`, `MatterBridgeAdapter`, `MqttShellyAdapter`), CLI (`ellmos-homecontrol`) und zweisprachiger Dokumentation.
