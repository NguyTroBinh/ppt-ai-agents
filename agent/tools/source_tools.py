"""
Source conversion tools -- PDF, DOCX, Excel, PPTX, Web to Markdown.

Wraps skills/ppt-master/scripts/source_to_md/*.py.

Each operation is exposed twice:
- Plain function (run_convert_*) for orchestrator to call directly.
- @function_tool wrapper (convert_*) for agents to call via tool calling.
"""

import subprocess
from pathlib import Path

from agents import function_tool

_SOURCE_TO_MD = (
    Path(__file__).parent.parent.parent
    / "skills" / "ppt-master" / "scripts" / "source_to_md"
)


def _convert(script: str, input_path: str) -> str:
    """Run a conversion script and return output."""
    result = subprocess.run(
        ["python3", str(_SOURCE_TO_MD / script), input_path],
        capture_output=True, text=True, timeout=300,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or "(no output)"


# --- Plain functions (called by orchestrator) ---

def run_convert_pdf(pdf_path: str) -> str:
    return _convert("pdf_to_md.py", pdf_path)

def run_convert_docx(doc_path: str) -> str:
    return _convert("doc_to_md.py", doc_path)

def run_convert_excel(excel_path: str) -> str:
    return _convert("excel_to_md.py", excel_path)

def run_convert_pptx(pptx_path: str) -> str:
    return _convert("ppt_to_md.py", pptx_path)

def run_convert_web(url: str) -> str:
    return _convert("web_to_md.py", url)


# --- Agent tool wrappers (called by LLM via tool calling) ---

@function_tool
def convert_pdf(pdf_path: str) -> str:
    """Convert a PDF file to Markdown.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Conversion result including output file path.
    """
    return run_convert_pdf(pdf_path)


@function_tool
def convert_docx(doc_path: str) -> str:
    """Convert a DOCX/HTML/EPUB document to Markdown.

    Args:
        doc_path: Path to the document file.

    Returns:
        Conversion result including output file path.
    """
    return run_convert_docx(doc_path)


@function_tool
def convert_excel(excel_path: str) -> str:
    """Convert an Excel workbook (.xlsx/.xlsm) to Markdown.

    Args:
        excel_path: Path to the Excel file.

    Returns:
        Conversion result including output file path.
    """
    return run_convert_excel(excel_path)


@function_tool
def convert_pptx(pptx_path: str) -> str:
    """Convert a PowerPoint file to Markdown.

    Args:
        pptx_path: Path to the PPTX file.

    Returns:
        Conversion result including output file path.
    """
    return run_convert_pptx(pptx_path)


@function_tool
def convert_web(url: str) -> str:
    """Convert a web page to Markdown.

    Args:
        url: URL of the web page.

    Returns:
        Conversion result including output file path.
    """
    return run_convert_web(url)
