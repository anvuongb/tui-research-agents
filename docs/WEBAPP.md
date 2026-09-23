# Webapp

Lightweight Flask webapp to browse collected/distilled papers alongside the TUI. Shares the same SQLite/ChromaDB storage.

## Stack

- **Flask** + Jinja2 — server-rendered HTML
- **Pico.css** (CDN) — dark theme
- **KaTeX** (CDN) — math rendering for `key_equations`
- **Pygments** — code syntax highlighting
- **markupsafe** — equation escaping (`render_equation` filter)
- Reuses: `storage/database.py`, `storage/models.py`, `utils/config.py`

A small `static/style.css` provides minor overrides on top of Pico.

## Directory

```
webapp/
├── __init__.py
├── main.py              # Flask app, routes, filters, async→sync wrappers
├── templates/
│   ├── base.html        # Pico.css dark shell, KaTeX, nav
│   ├── index.html       # Paper list, search, status filter
│   └── paper.html       # Detail: distillation, code, benchmarks
└── static/
    └── style.css         # Minor overrides only
```

## Routes

| Route | Query Params | Description |
|---|---|---|
| `GET /` | `?q=diffusion&status=distilled` | Paper list with search + filter |
| `GET /paper/<paper_id>` | — | Full detail: distillation, implementations (with code), benchmarks |
| `GET /pdf/<paper_id>` | — | Serve the downloaded PDF file |

## Features

| Feature | Implementation |
|---|---|
| Paper list | Cards with title, authors, source, year, status badge |
| Search | Text filter on title + abstract |
| Status filter | Dropdown: All / collected / distilled / implemented / prototyped / benchmarked |
| Distillation display | Summary, methodology, contributions, limitations in styled cards |
| Key equations | KaTeX-rendered via `render_equation` filter (HTML-escaped) |
| Implementation code | Pygments-highlighted `<pre>` blocks, one per version |
| Benchmarks | Metrics table with PASS/FAIL badges |
| PDF download | `/pdf/<id>` via `send_from_directory` |
| Nav | "Papers" link on every page, dark theme |

## Async → Sync Bridge

Flask is synchronous. The existing `Database` class is async (aiosqlite). Solution:

```python
# webapp/main.py
import asyncio

def _run(coro):
    return asyncio.run(coro)
```

Used in every route: `papers = _run(db.list_papers())`. Acceptable for a local single-user app.

## Security

- Binds `127.0.0.1` with `debug=False` (never expose the Werkzeug debugger).
- `render_equation` escapes HTML via `markupsafe.escape` before marking Markup (prevents stored XSS from LLM-derived equations).

## Dependencies

In `pyproject.toml` under `[project.optional-dependencies] web`:
```
flask>=3.0
pygments>=2.17
markupsafe>=2.1
```

## Entry Point

```bash
pip install -e ".[web]"
python -m webapp.main
# → http://127.0.0.1:5000
```

## Tests

`tests/unit/test_webapp.py` covers routes (index, filters, 404s) and the `render_equation` XSS regression.
