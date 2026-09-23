import asyncio
import os
import sys
from pathlib import Path

from flask import Flask, abort, render_template, request, send_from_directory
from markupsafe import Markup, escape
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tui_agents.storage.database import Database
from tui_agents.utils.config import Config

app = Flask(__name__)

_config = Config()
_db = Database(_config.database_path)


def _run(coro):
    return asyncio.run(coro)


@app.template_filter("highlight_code")
def highlight_code(code: str) -> str:
    if not code:
        return ""
    cleaned = code.strip()
    from tui_agents.agents.base import BaseAgent
    cleaned = BaseAgent.strip_code_fences(cleaned)
    result = highlight(cleaned, PythonLexer(), HtmlFormatter(style="monokai", linenos=False))
    return Markup(result)


@app.template_filter("render_equation")
def render_equation(eq: str) -> str:
    eq = eq.strip()
    if eq.startswith("$") and eq.endswith("$"):
        eq = eq[1:-1]
    return Markup(f"\\( {escape(eq)} \\)")


@app.context_processor
def inject_pygments_css():
    return {"pygments_css": HtmlFormatter(style="monokai").get_style_defs(".highlight")}


@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    papers = _run(_db.list_papers(limit=200))

    if status:
        papers = [p for p in papers if p.status == status]
    if query:
        papers = [p for p in papers if query.lower() in p.title.lower() or query.lower() in p.abstract.lower()]

    statuses = _run(_count_statuses())

    return render_template("index.html", papers=papers, query=query, status=status, statuses=statuses)


async def _count_statuses() -> dict[str, int]:
    counts = {}
    for s in ["collected", "distilled", "implemented", "prototyped", "benchmarked"]:
        counts[s] = await _db.count_papers(status=s)
    counts["all"] = await _db.count_papers()
    return counts


@app.route("/paper/<paper_id>")
def paper_detail(paper_id):
    paper = _run(_db.get_paper(paper_id))
    if not paper:
        return "Paper not found", 404

    distillation = _run(_db.get_distillation(paper_id))
    implementations = _run(_db.list_implementations(paper_id))
    benchmarks = _run(_db.get_benchmarks(paper_id))

    has_pdf = bool(paper.pdf_path and Path(paper.pdf_path).exists())

    return render_template(
        "paper.html",
        paper=paper,
        distillation=distillation,
        implementations=implementations,
        benchmarks=benchmarks,
        has_pdf=has_pdf,
    )


@app.route("/pdf/<paper_id>")
def serve_pdf(paper_id):
    paper = _run(_db.get_paper(paper_id))
    if not paper or not paper.pdf_path:
        abort(404)
    pdf = Path(paper.pdf_path)
    if not pdf.exists():
        abort(404)
    return send_from_directory(str(pdf.parent), pdf.name)


def main():
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
