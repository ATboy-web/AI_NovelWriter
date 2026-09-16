# AI NovelWriter v3.1.0

[![CI](https://github.com/ATboy-web/AI_NovelWriter/actions/workflows/ci.yml/badge.svg)](https://github.com/ATboy-web/AI_NovelWriter/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ATboy-web/AI_NovelWriter?label=release&color=blue)](https://github.com/ATboy-web/AI_NovelWriter/releases/latest)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT%20Modified-green.svg)](LICENSE)

An AI-powered long-form novel writing studio: **15 genres**, a **5-agent pipeline**, a
**panel-based workbench** (15 panels), **alternate-worldline branches with generational
inheritance**, and **multi-provider AI support with usage/cost accounting**.

Windows desktop ships as a single-file EXE. The repository also contains an Android app
(Kotlin + Compose), a FastAPI backend cluster, and a React web frontend.

> 中文文档请见 [README.md](README.md)（主要维护语言）。

![Workbench](docs/ui_review/after_01_toolkit.png)

## Download

| Platform | Version | Size | Link |
|----------|---------|------|------|
| **Windows** | **v3.1.0** | ~25 MB | [AI_NovelWriter.exe](https://github.com/ATboy-web/AI_NovelWriter/releases/latest) |
| Android | v4.0.1 (previous build) | ~10.9 MB | [AI_NovelWriter_v4.0.1.apk](https://github.com/ATboy-web/AI_NovelWriter/releases/tag/v2.16.0) |

Portable — no installation required. Configure an AI provider on first launch
(**Settings → AI Service**).

## Features

- **Creation engine** — outline → characters → chapters, fully automated.
  5 collaborating agents (PlotDesigner / WorldBuilder / Writer / Reviewer / Editor),
  multi-round AI review and revision, 15 genres, seamless continuation of finished novels.
- **Panel workbench** — 15 panels in 5 groups (materials, structure analysis, memory &
  summaries, **world-lines & generations**, operations). Every panel gets a breadcrumb bar,
  refresh button, status bar, and F5 / Ctrl+F / Esc shortcuts, provided by the panel host;
  registering a new panel is a one-line change. Any panel can also be **detached into its
  own window** to sit beside the main window; closing that window returns it automatically.
- **World-lines, branches and generations** — decision points are detected per chapter;
  a branch is a **openable sub-project** that joins the generation tree while remaining
  **read-only with respect to its parent** (writes inside the branch are allowed, escaping
  to the parent is refused by a path guard).
- **Character system** — five-dimension profiles, structured biographies (sections, arcs,
  provenance, token attribution), trope library, activity tracking.
- **Multi-provider AI** — provider registry with adapters for Ollama, OpenAI-compatible
  endpoints, Anthropic, DeepSeek, GLM, Qwen and Kimi; multiple saved API profiles;
  token usage, tiered pricing and cost estimation, plus balance queries where the vendor
  actually offers an API.
- **Export & reading** — TXT / EPUB / PDF / DOCX / Markdown export, multi-format reader.

## Requirements

- Windows 10/11 (64-bit), 4 GB RAM
- Either a local **Ollama** instance (14B+ model recommended) or a cloud API key

## Quick start

```bash
pip install -e ".[dev]"      # install with dev dependencies
python novel_app.py          # run the desktop app
python -m pytest -v          # run tests (tests/ + backend/tests)
ruff check app/ tests/       # lint
```

Build the Windows executable:

```bash
cd installer
python -m PyInstaller novel_app.spec --noconfirm   # → installer/dist/AI_NovelWriter.exe
```

Docker deployment for the backend services:

```bash
cp .env.example .env && docker-compose up -d
```

## Project layout

```
novel_app.py          thin desktop entry point
app/                  desktop application package
  panels/             panel framework (registry / host / legacy / ui_kit) + 15 panels
  providers/          multi-provider adapters, pricing, balance, reasoning models
  events/             thread-aware event bus
  timeline_store.py   unified timeline storage (fingerprint cache)
  lineage.py          generational inheritance + read-only-parent guard
backend/              ai-service (:8001) · novel-service (:8002) · shared middleware
frontend-react/       React web frontend
mobile-app/novel-app/ Android app (Kotlin + Compose)
installer/            PyInstaller specs and build scripts
tests/                71 files, including UI quality metrics and gates
docs/                 documentation (index: docs/README.md)
```

## Versioning & releases

`pyproject.toml` is the single source of truth for the version; `app.__version__` and this
repository's README follow it (enforced by `tests/test_version_consistency.py`).
Binaries are never committed — releases are distributed through
[GitHub Releases](https://github.com/ATboy-web/AI_NovelWriter/releases).
See [CHANGELOG.md](CHANGELOG.md) and [docs/VERSION_RELEASE_SPEC.md](docs/VERSION_RELEASE_SPEC.md).

## License

[MIT Modified](LICENSE) — free to use and modify; **commercial use must credit the origin**
(project name + GitHub link).
