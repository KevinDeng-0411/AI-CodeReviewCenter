"""C1-C：文件类型策略与轻量文档解析。"""

import io

import pytest
from docx import Document as DocxDocument
from pypdf import PdfWriter

from app.ai.services.document_parser import DocumentParserService


def test_upload_type_policy_matches_supported_extensions_and_mime():
    parser = DocumentParserService()
    assert parser.supports_upload("readme.md", "text/markdown")
    assert parser.supports_upload("README.MD", "text/plain; charset=utf-8")
    assert parser.supports_upload("manual.pdf", "application/pdf")
    assert parser.supports_upload("manual.docx", None)
    assert parser.supports_upload("manual.docx", "application/octet-stream")
    assert not parser.supports_upload("manual.pdf", "image/png")
    assert not parser.supports_upload("archive.zip", "application/octet-stream")
    assert not parser.supports_upload("no-extension", "text/plain")


def test_safe_filename_removes_client_paths():
    parser = DocumentParserService()
    assert parser.safe_filename("../../secret/readme.md") == "readme.md"
    assert parser.safe_filename(r"C:\fakepath\manual.docx") == "manual.docx"
    assert parser.safe_filename(None) == ""


def test_unknown_extension_does_not_fall_back_to_plain_text():
    with pytest.raises(ValueError, match="unsupported document type"):
        DocumentParserService._guess_content_type("payload.exe")


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("notes.txt", b"first line\nsecond line", "second line"),
        ("README.md", b"# Heading\n\nMarkdown body", "Markdown body"),
        ("page.html", b"<html><body><h1>Title</h1><p>HTML body</p></body></html>", "HTML body"),
    ],
)
async def test_parse_small_text_formats(filename, content, expected):
    text = await DocumentParserService().parse(content, filename)
    assert expected in text


async def test_parse_docx_with_declared_extra():
    document = DocxDocument()
    document.add_heading("DOCX heading")
    document.add_paragraph("DOCX body")
    buffer = io.BytesIO()
    document.save(buffer)

    text = await DocumentParserService().parse(buffer.getvalue(), "manual.docx")
    assert "DOCX heading" in text
    assert "DOCX body" in text


async def test_pdf_without_text_layer_returns_empty_for_route_to_reject():
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)

    text = await DocumentParserService().parse(buffer.getvalue(), "scan.pdf")
    assert text == ""
