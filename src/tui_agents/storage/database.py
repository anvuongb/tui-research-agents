import json
import os
from pathlib import Path
from typing import Any

import aiosqlite

from tui_agents.storage.models import (
    AgentRun,
    BenchmarkResult,
    Distillation,
    Implementation,
    Paper,
    StageStatus,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',
    abstract TEXT DEFAULT '',
    url TEXT,
    pdf_path TEXT,
    published_date TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    embedding_id TEXT,
    status TEXT DEFAULT 'new',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    agent_type TEXT NOT NULL,
    input_data TEXT,
    output_data TEXT,
    status TEXT DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS distillations (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    summary TEXT DEFAULT '',
    methodology TEXT DEFAULT '',
    contributions TEXT NOT NULL DEFAULT '[]',
    limitations TEXT NOT NULL DEFAULT '[]',
    key_equations TEXT NOT NULL DEFAULT '[]',
    related_work TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS implementations (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    code TEXT DEFAULT '',
    language TEXT DEFAULT 'python',
    dependencies TEXT NOT NULL DEFAULT '[]',
    tests TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    metrics TEXT NOT NULL DEFAULT '{}',
    compared_to_baseline INTEGER DEFAULT 0,
    passed_threshold INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS github_cache (
    query_key TEXT PRIMARY KEY,
    results TEXT NOT NULL,
    created_at TEXT NOT NULL,
    ttl_seconds INTEGER DEFAULT 86400
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_paper ON agent_runs(paper_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_type ON agent_runs(agent_type);
CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);
"""


def _row_to_paper(row: tuple) -> Paper:
    return Paper(
        id=row[0],
        source=row[1],
        source_id=row[2],
        title=row[3],
        authors=json.loads(row[4]),
        abstract=row[5] or "",
        url=row[6],
        pdf_path=row[7],
        published_date=row[8],
        tags=json.loads(row[9]),
        embedding_id=row[10],
        status=row[11],
        created_at=row[12],
        updated_at=row[13],
    )


def _row_to_agent_run(row: tuple) -> AgentRun:
    return AgentRun(
        id=row[0],
        paper_id=row[1],
        agent_type=row[2],
        input_data=json.loads(row[3]) if row[3] else None,
        output_data=json.loads(row[4]) if row[4] else None,
        status=row[5],
        started_at=row[6],
        completed_at=row[7],
        error_message=row[8],
        created_at=row[9],
    )


def _row_to_distillation(row: tuple) -> Distillation:
    return Distillation(
        id=row[0],
        paper_id=row[1],
        run_id=row[2],
        summary=row[3] or "",
        methodology=row[4] or "",
        contributions=json.loads(row[5]),
        limitations=json.loads(row[6]),
        key_equations=json.loads(row[7]),
        related_work=json.loads(row[8]),
        created_at=row[9],
    )


def _row_to_implementation(row: tuple) -> Implementation:
    return Implementation(
        id=row[0],
        paper_id=row[1],
        run_id=row[2],
        code=row[3] or "",
        language=row[4] or "python",
        dependencies=json.loads(row[5]),
        tests=row[6] or "",
        created_at=row[7],
    )


def _row_to_benchmark(row: tuple) -> BenchmarkResult:
    return BenchmarkResult(
        id=row[0],
        paper_id=row[1],
        run_id=row[2],
        metrics=json.loads(row[3]),
        compared_to_baseline=bool(row[4]),
        passed_threshold=bool(row[5]),
        created_at=row[6],
    )


class Database:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    async def _ensure_connected(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self._path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.executescript(SCHEMA)
            await self._conn.commit()
        return self._conn

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def upsert_paper(self, paper: Paper) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            """INSERT INTO papers (id, source, source_id, title, authors, abstract,
               url, pdf_path, published_date, tags, embedding_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               title=excluded.title, authors=excluded.authors, abstract=excluded.abstract,
               url=excluded.url, pdf_path=excluded.pdf_path, tags=excluded.tags,
               embedding_id=excluded.embedding_id, status=excluded.status,
               updated_at=excluded.updated_at""",
            (
                paper.id, paper.source.value, paper.source_id, paper.title,
                json.dumps(paper.authors), paper.abstract,
                paper.url, paper.pdf_path, paper.published_date,
                json.dumps(paper.tags), paper.embedding_id, paper.status,
                paper.created_at, paper.updated_at,
            ),
        )
        await conn.commit()

    async def get_paper(self, paper_id: str) -> Paper | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        rows = await cursor.fetchall()
        if not rows:
            return None
        return _row_to_paper(tuple(rows[0]))

    async def list_papers(
        self, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[Paper]:
        conn = await self._ensure_connected()
        if status:
            cursor = await conn.execute(
                "SELECT * FROM papers WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM papers ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        return [_row_to_paper(tuple(r)) for r in rows]

    async def count_papers(self, status: str | None = None) -> int:
        conn = await self._ensure_connected()
        if status:
            cursor = await conn.execute("SELECT COUNT(*) FROM papers WHERE status = ?", (status,))
        else:
            cursor = await conn.execute("SELECT COUNT(*) FROM papers")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def update_paper_status(self, paper_id: str, status: str) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            "UPDATE papers SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, paper_id),
        )
        await conn.commit()

    async def create_agent_run(self, run: AgentRun) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            """INSERT INTO agent_runs (id, paper_id, agent_type, input_data, output_data,
               status, started_at, completed_at, error_message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id, run.paper_id, run.agent_type.value,
                json.dumps(run.input_data) if run.input_data else None,
                json.dumps(run.output_data) if run.output_data else None,
                run.status.value, run.started_at, run.completed_at,
                run.error_message, run.created_at,
            ),
        )
        await conn.commit()

    async def update_agent_run(self, run: AgentRun) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            """UPDATE agent_runs SET output_data = ?, status = ?, completed_at = ?,
               error_message = ? WHERE id = ?""",
            (
                json.dumps(run.output_data) if run.output_data else None,
                run.status.value, run.completed_at,
                run.error_message, run.id,
            ),
        )
        await conn.commit()

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
        rows = await cursor.fetchall()
        if not rows:
            return None
        return _row_to_agent_run(tuple(rows[0]))

    async def get_runs_for_paper(self, paper_id: str) -> list[AgentRun]:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM agent_runs WHERE paper_id = ? ORDER BY created_at ASC",
            (paper_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_agent_run(tuple(r)) for r in rows]

    async def get_latest_run(self, paper_id: str, agent_type: str) -> AgentRun | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM agent_runs WHERE paper_id = ? AND agent_type = ? ORDER BY created_at DESC LIMIT 1",
            (paper_id, agent_type),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return _row_to_agent_run(tuple(rows[0]))

    async def save_distillation(self, d: Distillation) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            """INSERT OR REPLACE INTO distillations
               (id, paper_id, run_id, summary, methodology, contributions,
                limitations, key_equations, related_work, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                d.id, d.paper_id, d.run_id, d.summary, d.methodology,
                json.dumps(d.contributions), json.dumps(d.limitations),
                json.dumps(d.key_equations), json.dumps(d.related_work),
                d.created_at,
            ),
        )
        await conn.commit()

    async def get_distillation(self, paper_id: str) -> Distillation | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM distillations WHERE paper_id = ? ORDER BY created_at DESC LIMIT 1",
            (paper_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return _row_to_distillation(tuple(rows[0]))

    async def save_implementation(self, impl: Implementation) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            """INSERT INTO implementations
               (id, paper_id, run_id, code, language, dependencies, tests, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                impl.id, impl.paper_id, impl.run_id, impl.code, impl.language,
                json.dumps(impl.dependencies), impl.tests, impl.created_at,
            ),
        )
        await conn.commit()

    async def get_implementation(self, paper_id: str) -> Implementation | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM implementations WHERE paper_id = ? ORDER BY created_at DESC LIMIT 1",
            (paper_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return _row_to_implementation(tuple(rows[0]))

    async def get_implementation_by_id(self, impl_id: str) -> Implementation | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM implementations WHERE id = ?", (impl_id,)
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return _row_to_implementation(tuple(rows[0]))

    async def list_implementations(self, paper_id: str) -> list[Implementation]:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM implementations WHERE paper_id = ? ORDER BY created_at DESC",
            (paper_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_implementation(tuple(r)) for r in rows]

    async def delete_implementation(self, impl_id: str) -> None:
        conn = await self._ensure_connected()
        await conn.execute("DELETE FROM implementations WHERE id = ?", (impl_id,))
        await conn.commit()

    async def save_benchmark(self, b: BenchmarkResult) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            """INSERT OR REPLACE INTO benchmark_results
               (id, paper_id, run_id, metrics, compared_to_baseline,
                passed_threshold, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                b.id, b.paper_id, b.run_id, json.dumps(b.metrics),
                int(b.compared_to_baseline), int(b.passed_threshold),
                b.created_at,
            ),
        )
        await conn.commit()

    async def get_benchmarks(self, paper_id: str) -> list[BenchmarkResult]:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM benchmark_results WHERE paper_id = ? ORDER BY created_at DESC",
            (paper_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_benchmark(tuple(r)) for r in rows]

    async def get_latest_benchmark(self, paper_id: str) -> BenchmarkResult | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM benchmark_results WHERE paper_id = ? ORDER BY created_at DESC LIMIT 1",
            (paper_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return _row_to_benchmark(tuple(rows[0]))

    async def get_cached_github(self, query_key: str) -> list | None:
        conn = await self._ensure_connected()
        await conn.execute(
            "DELETE FROM github_cache WHERE created_at < datetime('now', '-' || ttl_seconds || ' seconds')"
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT results FROM github_cache WHERE query_key = ?", (query_key,)
        )
        row = await cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    async def set_cached_github(self, query_key: str, results: list, ttl_seconds: int = 86400) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            "INSERT OR REPLACE INTO github_cache (query_key, results, created_at, ttl_seconds) VALUES (?, ?, datetime('now'), ?)",
            (query_key, json.dumps(results), ttl_seconds),
        )
        await conn.commit()

    async def clear_github_cache(self) -> None:
        conn = await self._ensure_connected()
        await conn.execute("DELETE FROM github_cache")
        await conn.commit()

    async def delete_paper(self, paper_id: str) -> None:
        conn = await self._ensure_connected()
        await conn.execute("DELETE FROM benchmark_results WHERE paper_id = ?", (paper_id,))
        await conn.execute("DELETE FROM implementations WHERE paper_id = ?", (paper_id,))
        await conn.execute("DELETE FROM distillations WHERE paper_id = ?", (paper_id,))
        await conn.execute("DELETE FROM agent_runs WHERE paper_id = ?", (paper_id,))
        await conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        await conn.commit()
