"""Regression test: ensure all agent progress stage names are present
in PapersScreen.STAGE_ORDER and PipelineScreen stage_map.

When a new stage name is added to an agent's progress() calls, it must
also be added to STAGE_ORDER (for correct spinner auto-completion) and
to PipelineScreen's stage_map (for pipeline progress display).

Failure means: multiple spinners animating simultaneously, or missing
pipeline stage indicators. See Phase 3.5 bug fix for context.
"""

import ast
import re
from pathlib import Path


def _extract_stage_names_from_agents(project_root: Path) -> set[str]:
    """Scan all agent source files for progress() call stage names."""
    agents_dir = project_root / "src" / "tui_agents" / "agents"
    stages: set[str] = set()

    for py_file in agents_dir.glob("*.py"):
        if py_file.name in ("__init__.py", "base.py"):
            continue
        source = py_file.read_text()
        # Match: progress("stage_name", ...) or progress(stage_name, ...) or await progress("stage_name", ...)
        # Also match: await progress_cb("stage_name", ...)
        for match in re.finditer(r"""progress(?:_cb)?\s*\(\s*["']([^"']+)["']""", source):
            stages.add(match.group(1))

    return stages


def _extract_stage_order_keys(project_root: Path) -> set[str]:
    """Extract keys from PapersScreen.STAGE_ORDER dict."""
    papers_file = project_root / "src" / "tui_agents" / "app" / "screens" / "papers.py"
    source = papers_file.read_text()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PapersScreen":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "STAGE_ORDER":
                            if isinstance(item.value, ast.Dict):
                                keys: set[str] = set()
                                for k in item.value.keys:
                                    if isinstance(k, ast.Constant):
                                        keys.add(str(k.value))
                                return keys
    return set()


def _extract_stage_map_keys(project_root: Path) -> set[str]:
    """Extract keys from PipelineScreen stage_map dict."""
    pipeline_file = project_root / "src" / "tui_agents" / "app" / "screens" / "pipeline.py"
    source = pipeline_file.read_text()

    stages: set[str] = set()
    for match in re.finditer(r'"([^"]+)":\s*"([^"]+)"', source):
        stages.add(match.group(1))

    return stages


def test_all_agent_stages_in_stage_order(project_root: Path):
    """Every progress() stage name used by agents must be in STAGE_ORDER."""
    agent_stages = _extract_stage_names_from_agents(project_root)
    order_keys = _extract_stage_order_keys(project_root)

    missing = agent_stages - order_keys
    assert not missing, (
        f"Agent progress stages missing from PapersScreen.STAGE_ORDER:\n"
        f"  Missing: {sorted(missing)}\n"
        f"  STAGE_ORDER has: {sorted(order_keys)}\n"
        f"  Agent stages: {sorted(agent_stages)}\n\n"
        f"Add these stages to STAGE_ORDER in app/screens/papers.py "
        f"to fix spinner auto-completion."
    )


def test_all_agent_stages_in_pipeline_stage_map(project_root: Path):
    """Every progress() stage name used by agents must be in PipelineScreen stage_map."""
    agent_stages = _extract_stage_names_from_agents(project_root)
    map_keys = _extract_stage_map_keys(project_root)

    missing = agent_stages - map_keys
    assert not missing, (
        f"Agent progress stages missing from PipelineScreen stage_map:\n"
        f"  Missing: {sorted(missing)}\n"
        f"  stage_map has: {sorted(map_keys)}\n"
        f"  Agent stages: {sorted(agent_stages)}\n\n"
        f"Add these stages to stage_map in app/screens/pipeline.py "
        f"to fix pipeline progress display."
    )


def test_stage_order_has_no_duplicate_priorities(project_root: Path):
    """No two stages in STAGE_ORDER should share the same priority value."""
    papers_file = project_root / "src" / "tui_agents" / "app" / "screens" / "papers.py"
    source = papers_file.read_text()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PapersScreen":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "STAGE_ORDER":
                            if isinstance(item.value, ast.Dict):
                                values = []
                                for v in item.value.values:
                                    if isinstance(v, ast.Constant):
                                        values.append(v.value)
                                seen = set()
                                duplicates = set()
                                for val in values:
                                    if val in seen:
                                        duplicates.add(val)
                                    seen.add(val)
                                assert not duplicates, (
                                    f"STAGE_ORDER has duplicate priority values: {sorted(duplicates)}\n"
                                    f"Each stage must have a unique priority for correct auto-completion."
                                )
    # If no failures, test passes
