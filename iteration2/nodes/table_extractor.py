"""Sell-Side Table Extractor — Parse markdown tables into structured data.

Extracts financial estimate tables from sell-side reports and converts
them into AnalystEstimate objects for storage in the analyst_estimates table.
"""

import re
from typing import Optional

from iteration2.state import AnalystEstimate


def _parse_number(text: str) -> Optional[float]:
    """Parse a number from table cell text, handling commas and percentages."""
    if not text:
        return None
    cleaned = text.strip().replace(",", "").replace("₹", "").replace("$", "").rstrip("%")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _infer_unit(header: str, cell_value: str) -> str:
    """Infer the unit from the header or cell value."""
    header_lower = header.lower()
    cell_lower = cell_value.lower() if cell_value else ""

    if "margin" in header_lower or "%" in cell_value:
        return "%"
    if "₹ cr" in header_lower or "cr)" in header_lower:
        return "INR Cr"
    if "₹k" in header_lower or "₹ k" in header_lower:
        return "INR K"
    if "beds" in header_lower:
        return "Beds"
    if "arpob" in header_lower:
        return "INR K"
    if "occupancy" in header_lower:
        return "%"
    return "INR Cr"


def extract_estimates_from_table(table: dict, analyst: str = "",
                                  firm: str = "") -> list[AnalystEstimate]:
    """Convert a parsed markdown table into AnalystEstimate objects.

    Args:
        table: Dict from md_parser.extract_markdown_tables with 'headers' and 'rows'.
        analyst: Analyst name from document header.
        firm: Firm name from document header.

    Returns:
        List of AnalystEstimate objects for each metric+period combination.
    """
    headers = table.get("headers", [])
    rows = table.get("rows", [])

    if len(headers) < 2 or not rows:
        return []

    estimates = []
    period_headers = headers[1:]

    for row in rows:
        if len(row) < 2:
            continue
        metric_name = row[0].strip()
        if not metric_name:
            continue

        metric_name = re.sub(r"\s*\(.*?\)\s*$", "", metric_name).strip()

        for j, period in enumerate(period_headers):
            if j + 1 >= len(row):
                continue
            cell = row[j + 1].strip()
            value = _parse_number(cell)
            if value is None:
                continue

            unit = _infer_unit(metric_name, cell)
            period_clean = period.strip()

            estimates.append(AnalystEstimate(
                metric_name=metric_name,
                value=value,
                unit=unit,
                period=period_clean,
            ))

    return estimates
