from app.ingestion.html_to_markdown import html_to_markdown


def test_strips_html_tags():
    html = "<p>Hello <b>world</b></p>"
    result = html_to_markdown(html)
    assert "Hello" in result
    assert "world" in result
    assert "<b>" not in result
    assert "<p>" not in result


def test_preserves_heading_text():
    html = "<h1>Section One</h1><p>Content here.</p>"
    result = html_to_markdown(html)
    assert "Section One" in result
    assert "Content here." in result


def test_empty_body_returns_blank():
    result = html_to_markdown("<html><body></body></html>")
    assert result.strip() == ""


def test_returns_string():
    result = html_to_markdown("<p>text</p>")
    assert isinstance(result, str)
