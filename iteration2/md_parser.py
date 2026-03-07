"""Markdown document parser with section tagging.

Analogous to iteration1.pdf_parser for PDFs. Parses .md files with:
  - Header metadata extraction (date, analyst, firm, rating, target price)
  - Section tagging: [SECTION: Investment Thesis], [SECTION: Financial Estimates]
  - Markdown table detection and extraction as structured dicts
"""

import re
from typing import Optional


def extract_header_metadata(text: str) -> dict:
    """Extract structured metadata from the leading lines of a markdown doc.

    Looks for patterns like:
      **Date:** 15 November 2025
      **Analyst:** Priya Sharma, CFA | Healthcare Analyst
      **Rating: BUY** | Target Price: ...
      **Firm:** Goldman Sachs
    """
    meta: dict = {}
    lines = text.split("\n")[:30]
    joined = "\n".join(lines)

    date_match = re.search(r"\*\*Date:\*\*\s*(.+?)(?:\n|$)", joined)
    if date_match:
        meta["date"] = date_match.group(1).strip()

    analyst_match = re.search(r"\*\*Analyst:\*\*\s*(.+?)(?:\n|$)", joined)
    if analyst_match:
        meta["analyst"] = analyst_match.group(1).strip().split("|")[0].strip()

    firm_patterns = [
        re.search(r"^\*\*(.+?)\*\*\s*$", line)
        for line in lines[:10]
        if re.search(r"^\*\*(.+?)\*\*\s*$", line)
    ]
    for match in firm_patterns:
        name = match.group(1).strip()
        if name and "Date" not in name and "Analyst" not in name and "Rating" not in name:
            meta["firm"] = name
            break

    rating_match = re.search(
        r"\*\*Rating:\s*(\w+)\*\*|Rating:\s*(\w+)",
        joined,
    )
    if rating_match:
        meta["rating"] = (rating_match.group(1) or rating_match.group(2)).strip()

    tp_match = re.search(r"Target Price:\s*[₹$]?([\d,]+)", joined)
    if tp_match:
        meta["target_price"] = float(tp_match.group(1).replace(",", ""))

    cmp_match = re.search(r"CMP:\s*[₹$]?([\d,]+)", joined)
    if cmp_match:
        meta["cmp"] = float(cmp_match.group(1).replace(",", ""))

    ticker_match = re.search(r"\*\*Ticker:\*\*\s*(\S+)|Ticker:\s*(\S+)", joined)
    if ticker_match:
        meta["ticker"] = (ticker_match.group(1) or ticker_match.group(2)).strip()

    visited_match = re.search(r"\*\*Visited by:\*\*\s*(.+?)(?:\n|$)", joined)
    if visited_match:
        meta["visitor"] = visited_match.group(1).strip()

    conducted_match = re.search(r"\*\*Conducted by:\*\*\s*(.+?)(?:\n|$)", joined)
    if conducted_match:
        meta["visitor"] = conducted_match.group(1).strip()

    type_match = re.search(r"\*\*Type:\*\*\s*(.+?)(?:\n|$)", joined)
    if type_match:
        meta["visit_type"] = type_match.group(1).strip()

    return meta


def parse_md_with_section_tags(text: str) -> str:
    """Tag markdown sections analogous to [PAGE N] tags in PDFs.

    Converts ## headers into [SECTION: Header Text] tags so downstream
    LLM prompts can reference specific sections.
    """
    lines = text.split("\n")
    tagged_lines = []
    section_counter = 0

    for line in lines:
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            section_counter += 1
            heading_text = heading_match.group(2).strip()
            tagged_lines.append(f"\n[SECTION {section_counter}: {heading_text}]")
        else:
            tagged_lines.append(line)

    return "\n".join(tagged_lines)


def extract_markdown_tables(text: str) -> list[dict]:
    """Detect and extract markdown tables as structured dicts.

    Returns a list of tables, each as:
      {"headers": ["Metric", "Q2 FY26A", ...], "rows": [["Revenue", "2692", ...], ...],
       "raw_text": "the original markdown table text",
       "description": "Revenue estimates: FY26E 10,450 Cr, FY27E 12,200 Cr..."}
    """
    tables = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i + 1]):
            header_line = lines[i]
            headers = [cell.strip() for cell in header_line.split("|") if cell.strip()]

            table_lines = [lines[i], lines[i + 1]]
            j = i + 2
            rows = []
            while j < len(lines) and "|" in lines[j]:
                table_lines.append(lines[j])
                row_cells = [cell.strip() for cell in lines[j].split("|") if cell.strip()]
                rows.append(row_cells)
                j += 1

            raw_text = "\n".join(table_lines)
            desc_parts = []
            for row in rows:
                if row and headers:
                    metric = row[0] if row else ""
                    values = ", ".join(
                        f"{headers[k]}: {row[k]}" for k in range(1, min(len(headers), len(row)))
                    )
                    desc_parts.append(f"{metric} — {values}")
            description = "; ".join(desc_parts)

            tables.append({
                "headers": headers,
                "rows": rows,
                "raw_text": raw_text,
                "description": description,
            })
            i = j
        else:
            i += 1

    return tables


def parse_markdown_document(file_path: str) -> dict:
    """Full parse of a markdown document.

    Returns:
        {
            "raw_text": str,
            "section_tagged_text": str,
            "metadata": dict,
            "tables": list[dict],
            "file_path": str,
        }
    """
    with open(file_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    return {
        "raw_text": raw_text,
        "section_tagged_text": parse_md_with_section_tags(raw_text),
        "metadata": extract_header_metadata(raw_text),
        "tables": extract_markdown_tables(raw_text),
        "file_path": file_path,
    }
