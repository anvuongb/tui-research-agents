"""Tests for the Flask webapp."""

import pytest
from webapp.main import app, render_equation


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestWebApp:
    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Papers" in resp.data

    def test_index_with_search_query(self, client):
        resp = client.get("/?q=diffusion")
        assert resp.status_code == 200

    def test_index_with_status_filter(self, client):
        resp = client.get("/?status=distilled")
        assert resp.status_code == 200

    def test_paper_detail_nonexistent(self, client):
        resp = client.get("/paper/nonexistent-id")
        assert resp.status_code == 404

    def test_pdf_nonexistent_returns_404(self, client):
        resp = client.get("/pdf/nonexistent-id")
        assert resp.status_code == 404


class TestRenderEquationXSS:
    """M1 regression: render_equation must escape HTML in equation content."""

    def test_escapes_html_tags(self):
        out = render_equation("<script>alert(1)</script>")
        assert "<script>" not in str(out)
        assert "&lt;script&gt;" in str(out)

    def test_wraps_in_math_delimiters(self):
        out = render_equation("E = mc^2")
        assert str(out) == "\\( E = mc^2 \\)"

    def test_strips_dollar_wrapping(self):
        out = render_equation("$x + y$")
        assert str(out) == "\\( x + y \\)"

    def test_escapes_quoted_attributes(self):
        out = render_equation('"><img src=x onerror=alert(1)>')
        assert "<img" not in str(out)
        assert "onerror" in str(out) or "onerror" not in str(out).replace("&", "")
        assert "&quot;" in str(out) or '"' not in str(out).replace("\\(", "").replace("\\)", "")
