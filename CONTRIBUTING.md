# Beitragsrichtlinie / Contributing Guide

## Deutsch

Vielen Dank für Ihr Interesse, zu `ellmos-homecontrol` beizutragen!

### Wie Sie beitragen können

1. **Bug melden:** Erstellen Sie ein Issue mit dem Template für Bug-Reports (`bug`).
2. **Feature vorschlagen:** Erstellen Sie ein Issue mit dem Template für Feature-Requests (`enhancement`).
3. **Code beitragen:** Erstellen Sie einen Pull Request über einen dedizierten Branch.

### Entwicklungsumgebung einrichten

Voraussetzung ist Python 3.10 oder neuer.

```bash
pip install -e ".[dev]"
python -m ruff check src tests
python -m compileall -q src tests
python -m pytest -ra -v
```

### Code-Richtlinien

- **Stil & Linting:** PEP 8, geprüft über `ruff` (Zeilenlänge 120).
- **Encoding:** UTF-8 für alle Dateien; deutsche Dokumentation nutzt echte Umlaute (`ä`, `ö`, `ü`, `ß`).
- **Abhängigkeiten:** Keine externen Laufzeitabhängigkeiten (reine Python-Standardbibliothek).
- **Sicherheit:** Keine hartkodierten Zugangsdaten, Tokens oder lokalen Benutzerpfade. Änderungen an `FritzBoxAdapter.tr064_call` oder dem Bestätigungs-Gate erfordern entsprechende Tests.

### Pull Requests

1. Forken Sie das Repository oder erstellen Sie einen Feature-Branch (`git checkout -b feature/mein-feature`).
2. Führen Sie `ruff check`, `compileall` und `pytest` lokal aus.
3. Dokumentieren Sie relevante Änderungen in `CHANGELOG.md` unter `## [Unreleased]`.
4. Erstellen Sie einen Pull Request gegen `main`.

### Lizenzhinweis

Beiträge zu diesem Repository erfolgen unter der [MIT-Lizenz](LICENSE).

---

## English

Thank you for your interest in contributing to `ellmos-homecontrol`!

### How to Contribute

1. **Report bugs:** Open an issue using the bug report template (`bug`).
2. **Suggest features:** Open an issue using the feature request template (`enhancement`).
3. **Contribute code:** Submit a Pull Request from a dedicated branch.

### Setting Up Development

Requires Python 3.10 or newer.

```bash
pip install -e ".[dev]"
python -m ruff check src tests
python -m compileall -q src tests
python -m pytest -ra -v
```

### Code Guidelines

- **Style & Linting:** PEP 8, verified via `ruff` (line length 120).
- **Encoding:** UTF-8 for all files.
- **Dependencies:** Zero external runtime dependencies (Python standard library only).
- **Security:** No hardcoded credentials, tokens, or local user paths. Changes to `FritzBoxAdapter.tr064_call` or the high-load confirmation gate must include tests.

### Pull Requests

1. Fork the repository or create a feature branch (`git checkout -b feature/my-feature`).
2. Run `ruff check`, `compileall`, and `pytest` locally.
3. Document notable changes in `CHANGELOG.md` under `## [Unreleased]`.
4. Open a Pull Request targeting `main`.

### Licensing

Contributions are submitted under the [MIT License](LICENSE).
