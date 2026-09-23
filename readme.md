# TUI Research Agents — Terminal-based research agents

![demo](images/demo.png)

TUI app for managing LLM agents that collect, distill, implement, prototype, and benchmark research papers. Focused on diffusion models and optimal transport.

## Pipeline

```
Collector → Distiller → Implementer → Prototyper → Benchmarker
                                            ↑         │
                                            │  fail   │ pass
                                            └─────────┘  ✓
```

## Quick Start

```bash
git clone git@github.com:anvuongb/tui-research-agents.git
cd tui-research-agents
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
export OPENAI_API_KEY="sk-..."
python3 -m tui_agents.main
```

**Docker required** for benchmark execution.

### Webapp (optional)

```bash
pip install -e ".[web]"
python -m webapp.main
# → http://127.0.0.1:5000
```

## Keyboard Navigation

| Key | Tab |
|---|---|
| `Ctrl+D` | Dashboard |
| `Ctrl+P` | Papers |
| `Ctrl+L` | Pipeline |
| `Ctrl+B` | Benchmarks |
| `Ctrl+G` | Config |
| `q` | Quit |

## Workflow

1. `Ctrl+P` → type a query → Enter → search arXiv + Semantic Scholar
2. **Collect All** → downloads PDFs, extracts text, embeds in ChromaDB
3. Select a paper → **Distill** → LLM summary, methodology, contributions
4. **Implement** → LLM Python/PyTorch code (searches GitHub for references)
5. **Prototype** → runnable script with dependencies
6. **Run Prototype** → Docker execution (--network=none --read-only)
7. Benchmarks tab shows metrics and pass/fail

## Tests

```bash
source .venv/bin/activate
pytest tests/ -v          # 191 tests
pytest tests/unit/ -v     # Fast unit tests only
```

## Docs

- [Architecture & Pitfalls](docs/ARCHITECTURE.md)
- [Phase Plan](docs/PLAN.md)
- [Webapp](docs/WEBAPP.md)
