# TUI Research Agents — Project Documentation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Textual TUI (async)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │Dashboard │ │ Papers   │ │ Pipeline │ │ Config     │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│               Pipeline Orchestrator                      │
│  Collector → Distiller → Implementer → Prototyper →     │
│  Benchmarker ────── loop on failure ─────────────────┘  │
│  (full cascade delete_paper)                             │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    LLM Client                            │
│   OpenAI-compatible API / configurable base_url          │
│   Async chat_structured with JSON schema                 │
│   Lazy init — works without API key for collector        │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    Storage Layer                          │
│   SQLite (metadata, pipeline state, results)              │
│   ChromaDB (paper/insight/code embeddings, RAG)           │
│   Local files (PDFs, code/paper_id/impl_id[:8]/,         │
│   benchmarks/paper_id/run_id/)                           │
└─────────────────────────────────────────────────────────┘

                    Execution Layer
   ┌──────────────────────────────────────────────┐
   │  DockerRunner                                 │
   │  --network=none --read-only --memory=4g       │
   │  --cpus=2  python:3.11-slim                   │
   └──────────────────────────────────────────────┘
```

## Directory Structure

```
tui_agents/
├── config/default.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   └── PLAN.md
├── pyproject.toml
├── data/                        # .gitignored
│   ├── tui_agents.db
│   ├── chroma/
│   ├── papers/{paper_id}/{arxiv_id}.pdf
│   ├── code/{paper_id}/{impl_id[:8]}/    # impl, tests, proto, reqs
│   └── benchmarks/{paper_id}/{run_id}/   # bench script, output, summary
├── src/tui_agents/
│   ├── main.py
│   ├── app/
│   │   ├── tui.py
│   │   ├── messages.py
│   │   ├── screens/
│   │   │   ├── dashboard.py
│   │   │   ├── papers.py
│   │   │   ├── pipeline.py
│   │   │   ├── benchmarks.py
│   │   │   ├── config_screen.py
│   │   │   ├── code_viewer.py
│   │   │   ├── run_modal.py
│   │   │   ├── github_link_modal.py
│   │   │   └── confirm_modal.py
│   │   └── widgets/__init__.py
│   ├── agents/
│   │   ├── base.py                 # BaseAgent, strip_code_fences, _run_with_heartbeat
│   │   ├── collector.py
│   │   ├── distiller.py
│   │   ├── implementer.py
│   │   ├── prototyper.py
│   │   ├── benchmarker.py          # Generate benchmark, Docker run, evaluate
│   │   ├── runner.py               # Docker build/run with resource limits
│   │   ├── runtime_estimator.py    # LLM estimates CPU runtime
│   │   └── orchestrator.py
│   ├── llm/
│   │   ├── client.py
│   │   └── tools.py
│   ├── sources/
│   │   ├── arxiv.py
│   │   ├── semantic_scholar.py
│   │   ├── github.py
│   │   └── pdf.py
│   └── storage/
│       ├── database.py
│       ├── vector_store.py
│       └── models.py
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_deduplication.py
    │   ├── test_chunker.py
    │   ├── test_arxiv_client.py
    │   ├── test_semantic_scholar.py
    │   ├── test_collector_network.py
    │   ├── test_phase3_agents.py
    │   ├── test_phase35.py
    │   └── test_stage_order.py
    ├── integration/
    │   ├── test_storage.py
    │   ├── test_vector_store.py
    │   └── test_orchestrator.py
    └── tui/
        └── test_tui.py
```

---

## Completed Phases

### Phase 1 — Foundation ✅
- Project scaffold, dependencies
- SQLite schema (papers, agent_runs, distillations, implementations, benchmark_results)
- ChromaDB vector store
- LLM client abstraction
- BaseAgent class with run lifecycle
- Textual app shell with 5 tabbed screens

### Phase 2 — Collect + Distill ✅
- arXiv API client with category filter
- Semantic Scholar API client
- PDF text extractor and chunker
- Collector and Distiller agents
- Orchestrator with search/collect/distill methods
- Papers tab with search and DataTable

### Phase 2.5 — Stabilization ✅
- Unified screen base classes (Widget → Vertical)
- arXiv: 30s timeout, reduced OR clauses
- Semantic Scholar: graceful 429/timeout handling
- LLMClient lazy init
- 25 new tests

### Phase 3 — Implement + Prototype ✅
- ImplementerAgent: Python/PyTorch code generation
- PrototyperAgent: runnable script creation
- Pipeline stage mappings
- Papers tab: Implement/Prototype buttons

### Phase 3.5 — Enhanced Implementer + UI Polish ✅
- Full paper text loading from ChromaDB
- GitHub search with SQLite cache, LLM relevance evaluation, manual URL input
- Code viewer modal with syntax highlighting (tree-sitter python)
- Multi-implementation per paper (v1, v2...) with version navigation
- Cascade delete paper (DB + ChromaDB + files)
- Progress tracking with braille spinner and stage auto-completion
- Horizontal split layout (DataTable 60% | detail panel 40%)

### Phase 4 — Benchmarker + Loop (IN PROGRESS 🟡)
- **DONE**: RuntimeEstimator (LLM analyzes code for runtime estimate)
- **DONE**: DockerRunner (build/run with --network=none --read-only, timeout, limits)
- **DONE**: BenchmarkerAgent (generate benchmark, run via Docker, parse metrics, evaluate)
- **DONE**: RunModal (code preview, estimate display, confirm before execution)
- **DONE**: Orchestrator loop logic (implement → proto → bench → retry on failure)
- **DONE**: Pipeline stage mappings for benchmarker
- **DONE**: Benchmarks tab with results DataTable
- **DONE**: Run Prototype button in Papers tab
- **NEEDS FIX**: Prototype file path mismatch (prototyper saved to old path, benchmarker reads from new — fixed in code, needs re-prototype for existing papers)
- **TODO**: End-to-end Docker execution test
- **TODO**: Live stdout streaming during Docker run
- **TODO**: Cancel button during benchmark execution

---

## Test Suite

**144 tests** across 3 tiers:

| Tier | Files | Tests | What it covers |
|---|---|---|---|
| Unit | 9 files | 90+ tests | Dedup, chunker, arXiv queries, SS errors, collector network, implementer/prototyper structure, file save, prerequisite checks, GitHub client, cache, code viewer, stage order regression |
| Integration | 3 files | 28+ tests | SQLite CRUD, cascade delete, multi-implementation, ChromaDB ops, orchestrator delete (DB + Chroma + filesystem) |
| TUI | 1 file | 22+ tests | Widget hierarchy, tab navigation, keyboard bindings, progress accumulation, Run Prototype button |

```bash
source .venv/bin/activate && pytest tests/ -v
```

---

## Key Design Decisions

### Tab content uses Vertical, not Screen
`Screen` subclasses inside `TabPane` break tab switching — Screen's display management conflicts with TabbedContent. All tab content extends `Vertical`.

### Keyboard bindings use ctrl+ modifiers
Single-letter keys get captured by Input widgets. `ENABLE_COMMAND_PALETTE = False` frees `ctrl+p`.

### LLMClient is lazy-initialized
AsyncOpenAI client created on first call — collector works without API key.

### Implementations are versioned
Each "Implement" creates a new record. Files: `data/code/{paper_id}/{impl.id[:8]}/`.

### Progress tracking uses stage order
`STAGE_ORDER` dict maps stage names to priorities. New stages auto-complete earlier ones. Regression test in `test_stage_order.py` scans all agent source files to ensure every `progress()` call has an entry.

### Code fence stripping
`BaseAgent.strip_code_fences()` removes ```python wrappers at save AND display time.

---

## Known Pitfalls and Gotchas

### 1. `on_button_pressed` on Screen catches all buttons
Defining `on_button_pressed(self, event)` on a `Screen` subclass catches ALL `Button.Pressed` messages from children, including buttons from `Header`. Always use `@on(Button.Pressed, "#button-id")` with a CSS selector instead.

**Affected files:** `run_modal.py`, `confirm_modal.py`, `github_link_modal.py`, `code_viewer.py`

### 2. Screen inside TabPane breaks tab switching
`Screen` has its own display management that overrides `TabbedContent`'s `display: none/block` toggling. Use `Widget`/`Vertical` as base class for tab content.

**Regression test:** `TestScreenClassHierarchy` in `test_tui.py`

### 3. Auto-focusing widgets causes bounce-back
Calling `widget.focus()` inside `on_tab_activated` or related handlers latches focus to that widget, and Textual's focus manager pulls back the tab containing it on every subsequent switch. Use `set_timer(delay, callback)` to defer focus.

**Symptom:** Tab switches to non-Papers tabs and immediately bounces back.
**Fix:** `action_switch_tab` uses `set_timer(0.5, lambda: self._focus_screen(tab_id))`.

### 4. DataTable.clear() doesn't fully clear internal state
`table.clear()` removes rows but `DuplicateKey` errors still occur on subsequent `add_row` with the same keys. Wrap `add_row` in `try/except DuplicateKey: pass`.

**Affected:** `_refresh_library` in `papers.py`

### 5. Prototyper saves to wrong directory
Prototyper must save to `data/code/{paper_id}/{impl.id[:8]}/` (versioned), not `data/code/{paper_id}/` (flat). The benchmarker and Run button both read from the versioned path. Existing papers need re-prototype.

**Fix applied:** `_save_prototype_files` now takes `impl_id` parameter.

### 6. STAGE_ORDER must include every agent progress() stage
Any new `progress("stage_name", ...)` call in any agent must have an entry in `PapersScreen.STAGE_ORDER`, or multiple spinners animate simultaneously.

**Regression test:** `test_stage_order.py` scans all agent `.py` files and verifies.

### 7. RunModal callback uses asyncio.create_task, not run_worker
`self.run_worker()` from within a `push_screen` callback context doesn't always fire. Use `asyncio.create_task(worker_coro())` instead.

**Affected:** `on_run_prototype` handler in `papers.py`

### 8. Category filter too long hangs arXiv API
More than 4-5 OR clauses in arXiv `cat:` filter causes the API to hang. Current filter: 4 categories (`cs.LG OR cs.AI OR cs.CV OR stat.ML`).

**Test:** `TestDefaultCategoryFilter` in `test_arxiv_client.py`

### 9. LLM context overflow causes silent failures
When paper text + GitHub code + distillation exceed the model's context window, the LLM returns truncated/invalid JSON. The implementer's fallback path catches this, but the error message is generic. Check the progress label for specific error details.

**Note:** DeepSeek has 64K-128K context window, but output tokens are limited to `max_tokens: 16384`.

### 10. `push_screen` callback vs await pattern
`await app.push_screen(screen)` sometimes doesn't return the dismiss value in Textual 8.x. Use the callback pattern: `app.push_screen(screen, callback)` — proven to work reliably.

**Examples:** delete paper flow uses callback; Run Prototype uses callback.

### 11. Docker required for Phase 4
The benchmarker needs Docker installed and running. Without it, `DockerRunner.check_docker()` returns False and execution is blocked with an error message.

**Config:** `config/default.yaml` → `runner:` section controls timeout, memory, CPU.
