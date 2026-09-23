from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine

from tui_agents.agents.base import BaseAgent
from tui_agents.llm.client import LLMClient
from tui_agents.llm.tools import DISTILLER_TOOLS
from tui_agents.sources.pdf import estimate_token_count
from tui_agents.storage.database import Database
from tui_agents.storage.models import Distillation
from tui_agents.storage.vector_store import VectorStore


ProgressFn = Callable[[str, str, float], Coroutine[Any, Any, None]]

DISTILLER_SYSTEM_PROMPT = """You are an expert research scientist specializing in machine learning, with deep expertise in diffusion models and optimal transport. Your task is to thoroughly analyze a research paper and produce a structured distillation.

Follow these guidelines:
1. Read the entire paper carefully before producing your analysis
2. Focus on the core mathematical and algorithmic contributions
3. Identify the key equations in LaTeX format
4. Be precise about the methodology - explain the approach step by step
5. Note any limitations the authors acknowledge or that you can identify
6. List genuinely important related work that contextualizes this paper
7. Write in clear, technical English suitable for an ML researcher

Output a structured JSON response with these fields:
- summary: A comprehensive 2-3 paragraph summary covering the problem, approach, and key findings
- methodology: Detailed step-by-step description of the proposed method
- contributions: List of 3-5 key contributions as bullet-point strings
- limitations: List of 2-4 limitations or weaknesses
- key_equations: List of essential equations in LaTeX notation
- related_work: List of 3-5 notable related papers with brief relationship descriptions"""


class DistillerAgent(BaseAgent):
    agent_type = "distiller"

    def __init__(
        self,
        llm: LLMClient,
        database: Database,
        vector_store: VectorStore,
    ):
        super().__init__(llm, database)
        self.vector_store = vector_store

    async def distill(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> Distillation | None:
        paper = await self.db.get_paper(paper_id)
        if not paper:
            if progress:
                await progress("error", f"Paper not found: {paper_id}", 0.0)
            return None

        run_id = await self.start_run(paper_id)

        try:
            if progress:
                await progress("loading", f"Loading paper: {paper.title[:80]}", 0.05)

            paper_text = await self._gather_paper_text(paper_id)

            if not paper_text:
                abstract = paper.abstract or ""
                paper_text = f"Title: {paper.title}\n\nAbstract: {abstract}"

            token_estimate = estimate_token_count(paper_text)

            if progress:
                await progress("analyzing", f"Analyzing paper ({token_estimate} tokens, {len(paper_text)} chars)...", 0.1)

            distillation = await self._run_with_heartbeat(
                self._run_llm_distillation(paper.title, paper_text, paper_id, progress),
                progress, "analyzing",
            )

            if distillation:
                distillation.id = str(uuid.uuid4())
                distillation.paper_id = paper_id
                distillation.run_id = run_id
                distillation.created_at = datetime.now().isoformat()

                await self.db.save_distillation(distillation)
                await self.db.update_paper_status(paper_id, "distilled")

                output = {
                    "distillation_id": distillation.id,
                    "summary": distillation.summary[:200] + "...",
                }
                await self.complete_run(output)

                if progress:
                    await progress("done", f"Distillation complete: {paper.title[:80]}", 1.0)

                return distillation

            if progress:
                await progress("error", "LLM distillation returned no result", 0.0)
            return None

        except Exception as e:
            await self.fail_run(str(e))
            if progress:
                await progress("error", f"Distillation failed: {e}", 0.0)
            return None

    async def _gather_paper_text(self, paper_id: str) -> str:
        all_texts: list[str] = []

        try:
            existing = await asyncio.to_thread(
                self.vector_store.collection.get,
                where={"paper_id": paper_id},
                include=["documents", "metadatas"],
            )

            if existing and existing.get("documents"):
                docs_with_index = []
                for doc, meta in zip(existing["documents"], existing["metadatas"]):
                    if doc:
                        idx = int(meta.get("chunk_index", 0))
                        docs_with_index.append((idx, doc))
                docs_with_index.sort(key=lambda x: x[0])
                all_texts.extend(doc for _, doc in docs_with_index)
        except Exception as e:
            from tui_agents.utils.logging import get_logger
            get_logger().warning(f"Failed to load chunks for {paper_id}: {e}")

        if not all_texts:
            paper = await self.db.get_paper(paper_id)
            if paper and paper.pdf_path:
                try:
                    from tui_agents.sources.pdf import extract_text_from_pdf
                    text = await asyncio.to_thread(extract_text_from_pdf, paper.pdf_path)
                    if text:
                        all_texts.append(text)
                except Exception as e:
                    from tui_agents.utils.logging import get_logger
                    get_logger().warning(f"PDF re-extraction failed for {paper_id}: {e}")

        if not all_texts:
            paper = await self.db.get_paper(paper_id)
            if paper and paper.abstract:
                all_texts.append(f"Title: {paper.title}\n\nAbstract: {paper.abstract}")

        return "\n\n".join(all_texts)

    async def _run_llm_distillation(
        self,
        title: str,
        text: str,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> Distillation | None:
        max_chars = 40000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Text truncated due to length...]"
            if progress:
                await progress("analyzing", f"Paper truncated to {max_chars} chars for LLM context...", 0.15)

        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Comprehensive 2-3 paragraph summary"},
                "methodology": {"type": "string", "description": "Detailed step-by-step methodology"},
                "contributions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key contributions",
                },
                "limitations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Limitations and weaknesses",
                },
                "key_equations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key mathematical equations in LaTeX",
                },
                "related_work": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notable related work with descriptions",
                },
            },
            "required": ["summary", "methodology", "contributions", "limitations", "key_equations", "related_work"],
        }

        user_prompt = f"""Analyze the following research paper and produce a structured distillation.

Title: {title}

Paper Text:
{text}

Provide your analysis as a JSON object."""

        try:
            result = await self.llm.chat_structured(
                system_prompt=DISTILLER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=schema,
            )

            if "error" in result:
                if progress:
                    await progress("analyzing", f"JSON parse failed: {result.get('error', 'unknown')[:80]}", 0.2)
                from tui_agents.utils.logging import get_logger
                get_logger().warning(f"Distiller JSON parse failed: {result.get('error')}. Raw: {result.get('raw', '')[:200]}")
                return await self._fallback_tool_distillation(title, text, paper_id, progress)

            return Distillation(
                id="",
                paper_id=paper_id,
                run_id="",
                summary=result.get("summary", ""),
                methodology=result.get("methodology", ""),
                contributions=result.get("contributions", []),
                limitations=result.get("limitations", []),
                key_equations=result.get("key_equations", []),
                related_work=result.get("related_work", []),
            )

        except Exception as e:
            if progress:
                await progress("analyzing", f"LLM call failed: {e}", 0.2)
            from tui_agents.utils.logging import get_logger
            get_logger().exception(f"Distiller LLM call exception")
            return await self._fallback_tool_distillation(title, text, paper_id, progress)

    async def _fallback_tool_distillation(
        self,
        title: str,
        text: str,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> Distillation | None:
        messages = [
            {"role": "system", "content": DISTILLER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Title: {title}\n\nPaper Text:\n{text}"},
        ]

        try:
            collected_data = await self._collect_tool_payload(
                messages, DISTILLER_TOOLS, "save_distillation"
            )
            if collected_data:
                return Distillation(
                    id="",
                    paper_id=paper_id,
                    run_id="",
                    summary=collected_data.get("summary", ""),
                    methodology=collected_data.get("methodology", ""),
                    contributions=collected_data.get("contributions", []),
                    limitations=collected_data.get("limitations", []),
                    key_equations=collected_data.get("key_equations", []),
                    related_work=collected_data.get("related_work", []),
                )
        except Exception as e:
            if progress:
                await progress("error", f"Fallback distillation failed: {e}", 0.0)

        return None

    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        progress_fn = kwargs.get("progress_fn")
        distillation = await self.distill(paper_id, progress=progress_fn)
        if distillation:
            return {
                "status": "completed",
                "distillation_id": distillation.id,
                "summary": distillation.summary[:200],
            }
        return {"status": "failed", "error": "Distillation returned no result"}
