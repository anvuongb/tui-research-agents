# Phase 4 & 5 Plan

## Phase 4 — Benchmarker, Runner, Loop

**Status: IN PROGRESS 🟡**

Core agents and UI are built. Remaining work: path fixes for existing papers, Docker verification, live streaming, and cancel during benchmark execution.

### Completed ✅

| Component | File | Status |
|---|---|---|
| RuntimeEstimator | `agents/runtime_estimator.py` | ✅ Done |
| DockerRunner | `agents/runner.py` | ✅ Done |
| BenchmarkerAgent | `agents/benchmarker.py` | ✅ Done |
| RunModal | `app/screens/run_modal.py` | ✅ Done |
| Orchestrator loop | `agents/orchestrator.py` | ✅ Done |
| Run Prototype button | `app/screens/papers.py` | ✅ Done |
| Benchmarks tab | `app/screens/benchmarks.py` | ✅ Done |
| Pipeline stage map | `app/screens/pipeline.py` | ✅ Done |
| STAGE_ORDER entries | `app/screens/papers.py` | ✅ Done |
| Config | `config/default.yaml` | ✅ Done |

### Remaining

| Task | Priority | Notes |
|---|---|---|
| Fix prototype file path for existing papers | High | Prototyper now saves to versioned dir. User must re-run "Prototype Selected" for existing papers. |
| E2E Docker execution test | High | Verify build → run → capture metrics works on a real machine with Docker |
| Live stdout streaming in RunModal | Medium | Currently captured via pipe but not shown live in the modal after dismissal |
| Cancel button during benchmark | Medium | Docker run supports timeout, but no in-progress cancel |
| Docker not-installed UX | Medium | Better error message in RunModal before user clicks Run |
| Benchmark context injection in loop | Medium | `_run_llm_implementation` passes `previous_benchmark_context` but prompt section uses raw dict — could be cleaner |
| Loop iteration display in Dashboard | Low | Show "Paper X — iteration 2/5" |
| Loop test with mock pass/fail | Low | Tests for orchestrator loop logic |

### Loop Flow (implemented)

```
Implement → Prototype → Benchmark
    ↑                        │
    │   fail (iter < max)    │ pass
    └────────────────────────┘   ✓ done
    Context: "Previous scored 0.65. Fix loss function."
```

---

## Phase 5 — Polish

Final quality and UX improvements before v1.0.

### Agent Streaming
- LLM streaming for real-time output during distill/implement
- Show partial JSON as it arrives
- Cancel button to abort long-running operations

### Benchmark Visualization
- Charts/graphs of benchmark metrics over iterations (Rich tables/plots)
- Side-by-side comparison of multiple implementations

### Export
- Export paper + distillation + implementation as zip
- Export benchmark results as CSV/JSON
- Export all collected papers as a knowledge base

### Config Validation
- Validate config.yaml on startup
- Show warnings for common misconfigurations
- Test connection button for LLM and APIs

### Error Recovery
- Resume interrupted pipeline runs
- Mark failed stages clearly in Pipeline view
- One-click retry for failed stages

### UX
- Search history (recent queries)
- Paper tags/folders for organization
- Keyboard shortcut reference screen
- Dark/light theme toggle

### Documentation
- User guide with screenshots
- Developer guide for adding new agents
