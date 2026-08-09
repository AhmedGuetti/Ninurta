"""Document text extraction — read .pdf / .docx / .txt / .md resumes into plain text.

Dispatch table:
    .pdf   → pymupdf (fast, no OCR — text-based PDFs)
    .docx  → python-docx (paragraphs + table cells, in document order)
    .txt   → read directly
    .md    → read directly

Both libraries are lazy-imported so the core package works without them;
missing libraries raise a clear ImportError naming the extra to install.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

_console = Console()

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _extract_pdf(path: Path) -> str:
    try:
        import pymupdf  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "pymupdf is required to read PDF resumes. "
            "Run: pip install ninurta[documents]"
        ) from None

    parts: list[str] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                parts.append(text)
    return "\n\n".join(parts).strip()


def _extract_docx(path: Path) -> str:
    try:
        import docx  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "python-docx is required to read .docx resumes. "
            "Run: pip install ninurta[documents]"
        ) from None

    document = docx.Document(path)
    parts: list[str] = []

    # Walk body elements in document order so tables appear inline
    # where they actually are (python-docx paragraphs/tables split this).
    from docx.table import Table  # noqa: PLC0415
    from docx.text.paragraph import Paragraph  # noqa: PLC0415

    for element in document.element.body:
        if element.tag.endswith("}p"):
            para = Paragraph(element, document)
            if para.text.strip():
                parts.append(para.text)
        elif element.tag.endswith("}tbl"):
            table = Table(element, document)
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))

    return "\n".join(parts).strip()


def extract_text(path: str | Path) -> str:
    """Extract plain text from a resume file (.pdf/.docx/.txt/.md)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Supported: "
            f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix == ".docx":
        text = _extract_docx(path)
    else:
        text = path.read_text(encoding="utf-8")

    if not text.strip():
        _console.print(
            f"[bold yellow]⚠ No text found in {path} — "
            "it may be a scanned/image PDF.[/]"
        )
    return text.strip()
