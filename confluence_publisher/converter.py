from __future__ import annotations

import hashlib

import mistletoe
from mistletoe import Document
from mistletoe.base_renderer import BaseRenderer


class ConversionError(Exception):
    pass


class ConfluenceRenderer(BaseRenderer):
    def __init__(self, source_path: str = "<unknown>", **kwargs):
        super().__init__(**kwargs)
        self.source_path = source_path

    def render(self, token):
        node_type = type(token).__name__
        if node_type not in self.render_map:
            raise ConversionError(
                f"Unsupported Markdown element '{node_type}' in '{self.source_path}'. "
                f"Remove or convert to a supported syntax node."
            )
        return self.render_map[node_type](token)

    # --- Block tokens ---

    def render_document(self, token):
        return self.render_inner(token)

    def render_heading(self, token):
        inner = self.render_inner(token)
        return f"<h{token.level}>{inner}</h{token.level}>"

    def render_paragraph(self, token):
        return f"<p>{self.render_inner(token)}</p>"

    def render_quote(self, token):
        return f"<blockquote>{self.render_inner(token)}</blockquote>"

    def render_thematic_break(self, token):
        return "<hr/>"

    def render_block_code(self, token):
        # Handles both CodeFence (``` blocks) and BlockCode (indented blocks).
        # CodeFence carries a language attribute; BlockCode does not.
        code = token.children[0].content if token.children else ""
        language = getattr(token, "language", "") or ""
        if language == "mermaid":
            raise ConversionError(
                f"Mermaid diagrams are not supported until Phase 3 ('{self.source_path}')."
            )
        lang_param = (
            f'<ac:parameter ac:name="language">{_escape(language)}</ac:parameter>'
            if language
            else ""
        )
        return (
            f'<ac:structured-macro ac:name="code">'
            f"{lang_param}"
            f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
            f"</ac:structured-macro>"
        )

    def render_list(self, token):
        tag = "ol" if token.start is not None else "ul"
        return f"<{tag}>{self.render_inner(token)}</{tag}>"

    def render_list_item(self, token):
        return f"<li>{self.render_inner(token)}</li>"

    def render_table(self, token):
        raise ConversionError(
            f"Tables are not supported until Phase 3 ('{self.source_path}')."
        )

    def render_table_row(self, token):
        raise ConversionError(
            f"Tables are not supported until Phase 3 ('{self.source_path}')."
        )

    def render_table_cell(self, token):
        raise ConversionError(
            f"Tables are not supported until Phase 3 ('{self.source_path}')."
        )

    def render_strikethrough(self, token):
        raise ConversionError(
            f"Strikethrough (~~text~~) is not supported ('{self.source_path}'). "
            f"Remove or rewrite as plain text."
        )

    # --- Inline tokens ---

    def render_raw_text(self, token):
        return _escape(token.content)

    def render_strong(self, token):
        return f"<strong>{self.render_inner(token)}</strong>"

    def render_emphasis(self, token):
        return f"<em>{self.render_inner(token)}</em>"

    def render_inline_code(self, token):
        code = token.children[0].content
        return f"<code>{_escape(code)}</code>"

    def render_link(self, token):
        target = _escape_attr(token.target)
        return f'<a href="{target}">{self.render_inner(token)}</a>'

    def render_image(self, token):
        raise ConversionError(
            f"Images are not supported until Phase 2 ('{self.source_path}'). "
            f"Remove the image or wait for Phase 2."
        )

    def render_line_break(self, token):
        return " " if token.soft else "<br/>"

    def render_escape_sequence(self, token):
        return _escape(token.children[0].content)

    def render_auto_link(self, token):
        target = _escape_attr(token.children[0].content)
        return f'<a href="{target}">{target}</a>'

    def render_html_span(self, token):
        raise ConversionError(
            f"Inline HTML is not supported ('{self.source_path}'). "
            f"Remove or convert to Markdown."
        )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;")


def build_banner(source_path: str, commit_sha: str) -> str:
    return (
        f'<ac:structured-macro ac:name="info">'
        f"<ac:rich-text-body>"
        f"<p>This page is auto-generated from GitHub. "
        f"Manual edits will be overwritten on next publish.<br/>"
        f"Source: <code>{_escape(source_path)}</code> "
        f"@ <code>{_escape(commit_sha)}</code></p>"
        f"</ac:rich-text-body>"
        f"</ac:structured-macro>"
    )


def content_hash(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def convert(text: str, source_path: str, commit_sha: str) -> tuple[str, str]:
    """Return (body_without_banner, full_page_body) for a Markdown string.

    body_without_banner is used for change detection hashing.
    full_page_body is what gets published to Confluence.
    """
    with ConfluenceRenderer(source_path=source_path) as renderer:
        doc = Document(text)
        body = renderer.render(doc)
    banner = build_banner(source_path, commit_sha)
    return body, banner + body
