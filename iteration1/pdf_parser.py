"""Page-tagged PDF parser (deterministic — no LLM).

Loads a PDF page-by-page and tags each page's content with [PAGE N] markers.
This allows the LLM extraction step to cite exact page numbers for every
extracted value.

Example output:
    [PAGE 1]
    Max Healthcare Q1 FY26 Investor Presentation
    ...

    [PAGE 12]
    Financial Highlights
    Total Revenue from Operations: 2,574 Cr
    ...
"""

from langchain_community.document_loaders import PyPDFLoader


def parse_pdf_with_page_tags(pdf_path: str) -> str:
    """Load a PDF and return the full text with [PAGE N] markers.

    Each page's content is prefixed with a [PAGE N] tag so downstream
    LLM calls can reference specific pages in their citations.
    """
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()

    if not pages:
        raise ValueError(f"No text extracted from {pdf_path}")

    tagged_parts = []
    for page in pages:
        page_num = page.metadata.get("page", 0) + 1
        tagged_parts.append(f"[PAGE {page_num}]\n{page.page_content}")

    tagged_text = "\n\n".join(tagged_parts)

    print(f"[PDFParser] {pdf_path} — {len(pages)} pages, {len(tagged_text):,} chars (page-tagged)")
    return tagged_text
