import pytest
from confluence_publisher.converter import (
    ConversionError,
    ConfluenceRenderer,
    build_banner,
    content_hash,
    convert,
)
import mistletoe
from mistletoe import Document


def render(md: str, source: str = "test.md") -> str:
    with ConfluenceRenderer(source_path=source) as r:
        return r.render(Document(md))


# --- Headings ---

def test_heading_h1():
    assert render("# Hello") == "<h1>Hello</h1>"

def test_heading_h3():
    assert render("### Third") == "<h3>Third</h3>"

def test_heading_h6():
    assert render("###### Six") == "<h6>Six</h6>"


# --- Inline formatting ---

def test_bold():
    assert "<strong>bold</strong>" in render("**bold** text")

def test_italic():
    assert "<em>italic</em>" in render("_italic_ text")

def test_inline_code():
    assert "<code>x = 1</code>" in render("`x = 1`")

def test_inline_code_escapes_html():
    assert "<code>&lt;tag&gt;</code>" in render("`<tag>`")


# --- Paragraphs ---

def test_paragraph():
    assert render("Hello world") == "<p>Hello world</p>"

def test_html_escaped_in_text():
    assert render("a & b") == "<p>a &amp; b</p>"
    assert render("a < b") == "<p>a &lt; b</p>"


# --- Code blocks ---

def test_fenced_code_with_language():
    out = render("```python\nprint(1)\n```")
    assert 'ac:name="code"' in out
    assert 'ac:name="language">python' in out
    assert "<![CDATA[print(1)\n]]>" in out

def test_fenced_code_no_language():
    out = render("```\nsome code\n```")
    assert 'ac:name="code"' in out
    assert 'ac:name="language"' not in out
    assert "<![CDATA[some code\n]]>" in out

def test_mermaid_raises():
    with pytest.raises(ConversionError, match="Mermaid"):
        render("```mermaid\ngraph TD\n```")


# --- Lists ---

def test_unordered_list():
    out = render("- alpha\n- beta\n")
    assert out.startswith("<ul>")
    assert "<li>" in out
    assert "alpha" in out

def test_ordered_list():
    out = render("1. first\n2. second\n")
    assert out.startswith("<ol>")
    assert "first" in out

def test_nested_list():
    out = render("- parent\n  - child\n")
    assert out.count("<ul>") == 2


# --- Blockquote ---

def test_blockquote():
    out = render("> some quote\n")
    assert "<blockquote>" in out
    assert "some quote" in out


# --- Links ---

def test_external_link():
    out = render("[click here](https://example.com)")
    assert '<a href="https://example.com">click here</a>' in out

def test_link_href_escaping():
    out = render('[x](https://example.com/a&b"c)')
    assert "&amp;" in out
    assert "&quot;" in out


# --- Thematic break ---

def test_thematic_break():
    out = render("---\n")
    assert "<hr/>" in out


# --- Line breaks ---

def test_hard_line_break():
    out = render("line one  \nline two\n")
    assert "<br/>" in out

def test_soft_line_break_is_space():
    out = render("line one\nline two\n")
    assert "<br/>" not in out
    assert "line one" in out
    assert "line two" in out


# --- Unsupported nodes raise ConversionError ---

def test_image_raises():
    with pytest.raises(ConversionError, match="Phase 2"):
        render("![alt](image.png)")

def test_table_raises():
    with pytest.raises(ConversionError, match="Phase 3"):
        render("| a | b |\n|---|---|\n| 1 | 2 |\n")

def test_strikethrough_raises():
    with pytest.raises(ConversionError, match="Strikethrough"):
        render("~~deleted~~")


# --- Banner ---

def test_build_banner_contains_source():
    banner = build_banner("docs/arch.md", "abc1234")
    assert 'ac:name="info"' in banner
    assert "docs/arch.md" in banner
    assert "abc1234" in banner

def test_build_banner_escapes_path():
    banner = build_banner("docs/<special>.md", "sha")
    assert "&lt;special&gt;" in banner


# --- convert() ---

def test_convert_returns_tuple():
    body, full = convert("# Hello\n", "test.md", "abc1234")
    assert "<h1>Hello</h1>" in body
    assert "<h1>Hello</h1>" in full
    assert 'ac:name="info"' in full
    assert "abc1234" in full
    assert 'ac:name="info"' not in body

def test_convert_banner_prepended():
    body, full = convert("para\n", "f.md", "sha")
    assert full.startswith('<ac:structured-macro ac:name="info">')
    assert full.endswith("<p>para</p>")


# --- content_hash ---

def test_content_hash_deterministic():
    assert content_hash("hello") == content_hash("hello")

def test_content_hash_differs():
    assert content_hash("hello") != content_hash("world")


# --- Full sample doc ---

def test_sample_fixture(tmp_path):
    sample = (
        "# Title\n\nParagraph with **bold** and _italic_.\n\n"
        "```python\nx = 1\n```\n\n"
        "[link](https://example.com)\n\n"
        "> quote\n\n---\n"
    )
    body, full = convert(sample, "sample.md", "deadbeef")
    assert "<h1>Title</h1>" in body
    assert "<strong>bold</strong>" in body
    assert "<em>italic</em>" in body
    assert 'ac:name="code"' in body
    assert "<blockquote>" in body
    assert "<hr/>" in body
    assert "deadbeef" in full
