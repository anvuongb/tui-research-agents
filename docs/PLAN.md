# Phase 4 & 5 Plan

## Phase 4 — Benchmarker, Runner, Loop

**Status: DONE ✅**

Core agents, UI, loop, and correctness/hardening pass complete.

### Completed ✅

| Component | File | Status |
|---|---|---|
| RuntimeEstimator | `agents/runtime_estimator.py` | ✅ Done |
| DockerRunner | `agents/runner.py` | ✅ Done (+ entrypoint, build timeout, cidfile cleanup, hardening flags) |
| BenchmarkerAgent | `agents/benchmarker.py` | ✅ Done (+ requirements copy, entrypoint=benchmark.py, analysis persistence) |
| RunModal | `app/screens/run_modal.py` | ✅ Done |
| Orchestrator loop | `agents/orchestrator.py` | ✅ Done (+ analysis reaches retry prompt) |
| Run Prototype button | `app/screens/papers.py` + `papers_workers.py` | ✅ Done |
| Benchmarks tab | `app/screens/benchmarks.py` | ✅ Done (+ config-driven thresholds) |
| Pipeline stage map | `app/screens/pipeline.py` | ✅ Done (+ missing-widget guard) |
| STAGE_ORDER entries | `app/screens/papers.py` | ✅ Done (+ needs_github_link) |
| Config | `config/default.yaml` | ✅ Done (dead keys removed/wired) |
| Loop test with mock pass/fail | `tests/integration/test_run_pipeline.py` | ✅ Done |
| Analysis feedback regression | `tests/integration/test_benchmarker.py` | ✅ Done |
| E2E Docker execution test | — | ⬜ Remaining (needs real Docker daemon) |
| Live stdout streaming in RunModal | — | ⬜ Remaining |
| Cancel button during benchmark | — | ⬜ Remaining |

### Loop Flow (implemented + tested)

```
Implement → Prototype → Benchmark
    ↑                        │
    │   fail (iter < max)    │ pass
    └────────────────────────┘   ✓ done
    Context: {metrics, passed, analysis: "First attempt: loss stuck..."}
```

---

## Phase 5 — Polish

### Done in correctness/hardening pass ✅
- papers.py split (compose/routing vs workers vs detail)
- Tool-call fallback deduped into `BaseAgent._collect_tool_payload`
- Dead config removed (`iterations`, `watch_directory`, `theme`); wired `refresh_interval`, `pass_threshold`, `log_level`
- Unused symbols/imports pruned (COLLECTOR_TOOLS, BENCHMARKER_TOOLS, async arxiv dup, Semaphore, uvicorn tuning)
- Docs updated (readme env var/test count, ARCHITECTURE tree, WEBAPP routes)
- pyproject: markupsafe declared

### Remaining (future)

#### Agent Streaming
- LLM streaming for real-time output during distill/implement
- Show partial JSON as it arrives
- Cancel button to abort long-running operations

#### Benchmark Visualization
- Charts/graphs of benchmark metrics over iterations (Rich tables/plots)
- Side-by-side comparison of multiple implementations

#### Export
- Export paper + distillation + implementation as zip
- Export benchmark results as CSV/JSON
- Export all collected papers as a knowledge base

#### Config Validation
- Validate config.yaml on startup
- Show warnings for common misconfigurations
- Test connection button for LLM and APIs

#### Error Recovery
- Resume interrupted pipeline runs
- Mark failed stages clearly in Pipeline view
- One-click retry for failed stages

#### UX
- Search history (recent queries)
- Paper tags/folders for organization
- Keyboard shortcut reference screen
- Dark/light theme toggle

#### Documentation
- User guide with screenshots
- Developer guide for adding new agents

#### Docker
- E2E Docker execution test on a machine with Docker daemon
- Live stdout streaming in RunModal
- Cancel button during benchmark
