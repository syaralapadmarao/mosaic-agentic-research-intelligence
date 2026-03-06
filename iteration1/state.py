"""State definitions and Pydantic models for the Earnings Intelligence Pipeline.

Models cover:
  - Metric schema (loaded from JSON)
  - Document classification (from classifier node)
  - Metric extraction (LLM output with citations)
  - Validation results (LLM sanity checks)
  - Guidance extraction (from transcript flow)
  - Guidance deltas (quarter-over-quarter changes)
  - Pipeline state (LangGraph TypedDict)
"""

from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Metric Schema (loaded from schemas/*.json)
# ---------------------------------------------------------------------------

class MetricDefinition(BaseModel):
    """A single metric definition from the company schema."""
    name: str
    type: str = "direct"
    unit: str
    aliases: List[str] = Field(default_factory=list)
    fallback_formula: Optional[str] = None
    fallback_requires: List[str] = Field(default_factory=list)


class MetricSchema(BaseModel):
    """Full company metric schema loaded from JSON."""
    company: str
    ticker: Optional[str] = None
    sector: Optional[str] = None
    currency: str = "INR"
    metrics: List[MetricDefinition]

    def metric_names(self) -> list[str]:
        return [m.name for m in self.metrics]

    def get_metric(self, name: str) -> Optional[MetricDefinition]:
        for m in self.metrics:
            if m.name == name:
                return m
        return None


# ---------------------------------------------------------------------------
# 2. Document Classification (from classifier node — kept from before)
# ---------------------------------------------------------------------------

class DocumentClassification(BaseModel):
    """Structured output from the LLM classifier."""
    doc_type: str = Field(
        description=(
            "Document type. One of: earnings_call, broker_note, "
            "10-K, 10-Q, press_release, investor_presentation, other"
        )
    )
    company: str = Field(description="Company name mentioned in the document")
    ticker: Optional[str] = Field(default=None, description="Stock ticker symbol if identifiable")
    period: str = Field(description="Fiscal period covered, e.g. 'Q1 FY26' or 'FY2025'")
    doc_date: Optional[str] = Field(default=None, description="Document date in YYYY-MM-DD if identifiable")
    confidence: float = Field(description="Classification confidence between 0.0 and 1.0")
    summary: str = Field(description="One-sentence summary of the document's purpose")


# ---------------------------------------------------------------------------
# 3. Extracted Metric (LLM output — one per metric)
# ---------------------------------------------------------------------------

class ExtractedMetric(BaseModel):
    """A single metric extracted by the LLM from the document."""
    metric_name: str = Field(description="Metric name matching the schema, e.g. 'Revenue'")
    value: Optional[float] = Field(default=None, description="Numeric value extracted (null if not found)")
    raw_value: Optional[str] = Field(default=None, description="Original text as it appears in the document, e.g. '2,574 Cr'")
    unit: str = Field(description="Unit of measurement, e.g. 'INR Cr', '%', 'Beds'")
    page: Optional[int] = Field(default=None, description="Page number where this value appears")
    passage: Optional[str] = Field(default=None, description="Exact text passage containing this value (max 50 words)")
    found: bool = Field(default=True, description="Whether the metric was found in the document")
    note: Optional[str] = Field(default=None, description="Explanation if metric was not found or is uncertain")


class ExtractionResult(BaseModel):
    """Full extraction output — list of metrics from one document."""
    metrics: List[ExtractedMetric] = Field(description="One entry per metric in the schema")


# ---------------------------------------------------------------------------
# 4. Validation Result (LLM output — one per metric)
# ---------------------------------------------------------------------------

class MetricValidation(BaseModel):
    """Validation result for a single metric."""
    metric_name: str = Field(description="Name of the metric being validated")
    status: str = Field(description="'pass' if the value looks correct, 'flag' if suspicious")
    issue: Optional[str] = Field(default=None, description="Description of the issue if flagged")


class ValidationResult(BaseModel):
    """Full validation output for all metrics."""
    results: List[MetricValidation] = Field(description="One entry per metric")
    overall_status: str = Field(description="'clean' if all pass, 'review_needed' if any flagged")


# ---------------------------------------------------------------------------
# 5. Guidance Extraction (from transcript flow)
# ---------------------------------------------------------------------------

GUIDANCE_TOPICS = [
    "Financial Outlook",
    "Capacity Expansion",
    "Operational Efficiency",
    "Capital Allocation",
    "Strategic Initiatives",
    "Market & Competition",
    "Regulatory & Risk",
]


SENTIMENT_LEVELS = ["very_bullish", "bullish", "neutral", "cautious", "very_cautious"]

SENTIMENT_ARROWS = {
    "very_bullish": "↑",
    "bullish": "↗",
    "neutral": "→",
    "cautious": "↘",
    "very_cautious": "↓",
}

SENTIMENT_COLORS = {
    "very_bullish": "#22c55e",
    "bullish": "#86efac",
    "neutral": "#a3a3a3",
    "cautious": "#fbbf24",
    "very_cautious": "#ef4444",
}


class GuidanceItem(BaseModel):
    """A single forward-looking guidance statement extracted from a transcript."""
    topic: str = Field(description="Topic category from the taxonomy")
    statement: str = Field(description="The forward-looking guidance statement (max 2 sentences)")
    sentiment: str = Field(
        description="Sentiment of this guidance: 'very_bullish', 'bullish', 'neutral', 'cautious', or 'very_cautious'"
    )
    speaker: Optional[str] = Field(default=None, description="Name of the person who made the statement")
    timeframe: Optional[str] = Field(default=None, description="Timeframe mentioned, e.g. 'FY26', 'next 2-3 years', 'Q2 FY26'")
    page: Optional[int] = Field(default=None, description="Page number where this statement appears")
    passage: Optional[str] = Field(default=None, description="Exact passage containing the statement (max 60 words)")


class GuidanceExtractionResult(BaseModel):
    """Full guidance extraction output from one transcript."""
    items: List[GuidanceItem] = Field(description="All forward-looking guidance statements found")


# ---------------------------------------------------------------------------
# 6. Guidance Delta Detection (quarter-over-quarter changes)
# ---------------------------------------------------------------------------

class GuidanceDelta(BaseModel):
    """A detected change in guidance between the current and prior quarter."""
    topic: str = Field(description="Topic category")
    change_type: str = Field(description="One of: 'new', 'upgraded', 'downgraded', 'reiterated', 'removed'")
    current_statement: Optional[str] = Field(default=None, description="Guidance from current quarter")
    prior_statement: Optional[str] = Field(default=None, description="Guidance from prior quarter (if applicable)")
    summary: str = Field(description="One-sentence description of the change")


class DeltaDetectionResult(BaseModel):
    """Full delta detection output comparing two quarters."""
    deltas: List[GuidanceDelta] = Field(description="All detected changes")
    prior_quarter: Optional[str] = Field(default=None, description="The quarter being compared against")


# ---------------------------------------------------------------------------
# 7. Pipeline State (LangGraph TypedDict)
# ---------------------------------------------------------------------------

PRESENTATION_ROUTE = "presentation"
TRANSCRIPT_ROUTE = "transcript"


class PipelineState(TypedDict):
    """State that flows through the LangGraph pipeline.

    Presentation flow (Workflow A):
      classify → parse_pdf → extract_metrics → calculate_metrics
      → validate_metrics → assemble_table → END

    Transcript flow (Workflow B):
      classify → parse_pdf → extract_guidance → detect_deltas
      → assemble_guidance → END
    """
    # Input
    raw_text: str
    page_tagged_text: str
    file_name: str
    pdf_path: str
    company: str
    quarter: str

    # Classifier
    classification: Optional[DocumentClassification]
    route: Optional[str]

    # Schema
    metric_schema: Optional[MetricSchema]

    # --- Workflow A: Presentation → Metrics ---
    extracted_metrics: Optional[List[ExtractedMetric]]
    calculated_metrics: Optional[List[ExtractedMetric]]
    validation: Optional[ValidationResult]
    metrics_table: Optional[dict]

    # --- Workflow B: Transcript → Guidance ---
    guidance_items: Optional[List[GuidanceItem]]
    guidance_deltas: Optional[DeltaDetectionResult]
    guidance_table: Optional[dict]
