"""Pydantic models and pipeline state for Iteration 2.

Extends iteration1.state with multi-source models:
  - Source document registry
  - Sell-side reports (ratings, estimates, thesis)
  - Visit note insights
  - MNPI screening
  - Query analysis and retrieval
  - Consensus divergence
  - Mosaic completeness
  - Research answer output
"""

from __future__ import annotations

from typing import Any, List, Optional, TypedDict

from pydantic import BaseModel, Field

from iteration1.state import (
    DocumentClassification,
    ExtractedMetric,
    ExtractionResult,
    GuidanceDelta,
    GuidanceItem,
    MetricSchema,
    PipelineState as Iter1PipelineState,
    PRESENTATION_ROUTE,
    TRANSCRIPT_ROUTE,
)

# Route constants for new document types
SELL_SIDE_ROUTE = "sell_side"
VISIT_NOTE_ROUTE = "visit_note"
BROKER_EMAIL_ROUTE = "broker_email"

# Source-type namespace mapping
NAMESPACE_DISCLOSURE = "disclosure"
NAMESPACE_OPINION = "opinion"
NAMESPACE_FIELD_DATA = "field_data"

SOURCE_TYPE_MAP = {
    "transcript": NAMESPACE_DISCLOSURE,
    "investor_presentation": NAMESPACE_DISCLOSURE,
    "earnings_call": NAMESPACE_DISCLOSURE,
    "sell_side": NAMESPACE_OPINION,
    "broker_email": NAMESPACE_OPINION,
    "visit_note": NAMESPACE_FIELD_DATA,
}

FRESHNESS_THRESHOLDS_DAYS = {
    NAMESPACE_DISCLOSURE: 90,
    NAMESPACE_OPINION: 60,
    NAMESPACE_FIELD_DATA: 90,
}


# ---------------------------------------------------------------------------
# Source Document Registry
# ---------------------------------------------------------------------------

class SourceDocument(BaseModel):
    """Metadata for any ingested document."""
    source_type: str = Field(description="Namespace: 'disclosure', 'opinion', or 'field_data'")
    doc_type: str = Field(description="e.g. 'transcript', 'sell_side', 'visit_note', 'broker_email'")
    file_name: str
    file_path: str
    company: str
    ticker: Optional[str] = None
    sector: Optional[str] = None
    region: Optional[str] = None
    date: Optional[str] = None
    broker_name: Optional[str] = None
    analyst: Optional[str] = None


# ---------------------------------------------------------------------------
# Sell-Side Report Models (Workflow C)
# ---------------------------------------------------------------------------

class AnalystEstimate(BaseModel):
    """A single forward-looking financial estimate from a sell-side report."""
    metric_name: str = Field(description="e.g. 'Revenue', 'EBITDA', 'PAT'")
    value: Optional[float] = Field(default=None)
    unit: str = Field(default="INR Cr")
    period: str = Field(description="e.g. 'Q2 FY26A', 'FY27E', 'FY28E'")


class SellSideReport(BaseModel):
    """Structured extraction from a sell-side analyst report."""
    rating: str = Field(description="BUY, HOLD, SELL, NEUTRAL, REDUCE, UNDERWEIGHT, OVERWEIGHT")
    target_price: Optional[float] = None
    cmp: Optional[float] = Field(default=None, description="Current market price at report date")
    analyst: str = Field(description="Analyst name")
    firm: str = Field(description="Brokerage firm name")
    date: Optional[str] = Field(default=None, description="Report date YYYY-MM-DD")
    key_thesis: str = Field(description="1-2 sentence investment thesis summary")
    risk_factors: List[str] = Field(default_factory=list, description="Key risk factors identified")
    estimates: List[AnalystEstimate] = Field(default_factory=list, description="Financial estimates table")


# ---------------------------------------------------------------------------
# Visit Note Models (Workflow D)
# ---------------------------------------------------------------------------

class VisitNoteInsight(BaseModel):
    """A single observation extracted from a visit note or channel check."""
    topic: str = Field(description="Topic category matching guidance taxonomy where possible")
    observation: str = Field(description="Key observation (1-2 sentences)")
    sentiment: str = Field(description="'very_bullish', 'bullish', 'neutral', 'cautious', 'very_cautious'")
    conviction: str = Field(description="'strong_positive', 'incrementally_positive', 'neutral', 'incrementally_negative', 'strong_negative'")
    source_person: Optional[str] = Field(default=None, description="Person who provided the insight")


class VisitNoteExtraction(BaseModel):
    """Full extraction from a visit note."""
    visit_type: str = Field(description="'site_visit', 'management_meeting', 'channel_check', 'doctor_survey'")
    date: Optional[str] = None
    visitor: Optional[str] = None
    overall_conviction: str = Field(default="neutral")
    insights: List[VisitNoteInsight] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# MNPI Screening
# ---------------------------------------------------------------------------

class MNPIScreenResult(BaseModel):
    """Result of pre-ingestion MNPI screening."""
    is_mnpi: bool = Field(description="True if material non-public information detected")
    confidence: float = Field(default=0.0, description="Detection confidence 0.0-1.0")
    reason: Optional[str] = Field(default=None, description="Why flagged as MNPI")
    pii_entities: List[str] = Field(default_factory=list, description="PII entities detected and scrubbed")
    scrubbed_text: Optional[str] = Field(default=None, description="Text after PII scrubbing")


# ---------------------------------------------------------------------------
# Query Analysis (Online Pipeline)
# ---------------------------------------------------------------------------

class MetadataFilters(BaseModel):
    """Structured metadata filters extracted from query analysis."""
    source_type: Optional[str] = Field(default=None, description="'disclosure', 'opinion', or 'field_data'")
    doc_type: Optional[str] = Field(default=None, description="e.g. 'transcript', 'sell_side', 'visit_note'")
    date_range: Optional[str] = Field(default=None, description="Time window if implied, e.g. 'last 90 days'")


class QueryIntent(BaseModel):
    """LLM-analyzed intent and reformulations for an analyst query."""
    intent: str = Field(description="'STRUCTURED', 'UNSTRUCTURED', or 'HYBRID'")
    original_query: str
    reformulations: List[str] = Field(default_factory=list, description="3 alternative phrasings")
    taxonomy_terms: List[str] = Field(default_factory=list, description="Relevant topic terms from taxonomy")
    metadata_filters: MetadataFilters = Field(default_factory=MetadataFilters, description="Extracted filters from query")
    is_investment_query: bool = Field(default=True, description="False if query is off-topic")
    rejection_reason: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Retrieved Chunks
# ---------------------------------------------------------------------------

class RetrievedChunk(BaseModel):
    """A chunk retrieved from vector store or SQL with full metadata."""
    text: str
    source_type: str = Field(description="'disclosure', 'opinion', or 'field_data'")
    doc_type: str
    company: str
    file_name: str
    section: Optional[str] = None
    date: Optional[str] = None
    broker_name: Optional[str] = None
    relevance_score: float = Field(default=0.0)
    is_stale: bool = Field(default=False)
    freshness_days: int = Field(default=0)
    relevance_label: Optional[str] = Field(default=None, description="RELEVANT, TANGENTIAL, or IRRELEVANT")


# ---------------------------------------------------------------------------
# Consensus Divergence
# ---------------------------------------------------------------------------

class ConsensusDivergence(BaseModel):
    """Detected disagreement between OPINION sources."""
    metric_or_topic: str
    sources_agree: bool
    view_a: str = Field(description="e.g. 'Goldman (BUY): sees 16% revenue growth'")
    view_b: str = Field(description="e.g. 'Macquarie (NEUTRAL): sees 11% growth'")
    divergence_summary: str


# ---------------------------------------------------------------------------
# Mosaic Completeness
# ---------------------------------------------------------------------------

class MosaicCompleteness(BaseModel):
    """Tracks which source types are represented in the answer."""
    disclosure_present: bool = False
    opinion_present: bool = False
    field_data_present: bool = False
    missing_types: List[str] = Field(default_factory=list)
    completeness_score: float = Field(default=0.0, description="0.0 to 1.0")


# ---------------------------------------------------------------------------
# Research Answer (Final Output)
# ---------------------------------------------------------------------------

RESPONSE_STATES = [
    "Normal",
    "Partially Verified",
    "Stale",
    "No Results",
    "SQL Fallback",
    "MNPI Block",
    "Consensus Divergence",
]


class SourceBadge(BaseModel):
    """Inline source attribution for a claim in the answer."""
    claim_index: int
    source_type: str
    doc_ref: str
    date: Optional[str] = None
    broker_name: Optional[str] = None


class ResearchAnswer(BaseModel):
    """Complete decorated research answer."""
    answer: str
    citations: List[dict] = Field(default_factory=list)
    source_badges: List[SourceBadge] = Field(default_factory=list)
    mosaic: MosaicCompleteness = Field(default_factory=MosaicCompleteness)
    divergences: List[ConsensusDivergence] = Field(default_factory=list)
    stale_warnings: List[dict] = Field(default_factory=list)
    response_state: str = Field(default="Normal")
    cached: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Extended Pipeline State (LangGraph TypedDict)
# ---------------------------------------------------------------------------

class OfflinePipelineState(TypedDict):
    """State for the offline document ingestion pipeline."""
    raw_text: str
    file_name: str
    file_path: str
    pdf_path: Optional[str]
    company: str
    quarter: str

    # MNPI screening
    mnpi_result: Optional[MNPIScreenResult]
    scrubbed_text: Optional[str]

    # Classification
    classification: Optional[DocumentClassification]
    route: Optional[str]
    source_type: Optional[str]

    # Schema (reused from iter1)
    metric_schema: Optional[MetricSchema]

    # Workflow A outputs (presentations → metrics)
    page_tagged_text: Optional[str]
    extracted_metrics: Optional[List[ExtractedMetric]]
    calculated_metrics: Optional[List[ExtractedMetric]]
    validation: Optional[Any]
    metrics_table: Optional[dict]

    # Workflow B outputs (transcripts → guidance)
    guidance_items: Optional[List[GuidanceItem]]
    guidance_deltas: Optional[Any]
    guidance_table: Optional[dict]

    # Workflow C outputs (sell-side reports)
    sell_side_report: Optional[SellSideReport]

    # Workflow D outputs (visit notes)
    visit_note_extraction: Optional[VisitNoteExtraction]

    # Source document metadata
    source_document: Optional[SourceDocument]

    # Chunking outputs
    chunks: Optional[List[dict]]


class OnlinePipelineState(TypedDict):
    """State for the online research query pipeline."""
    query: str
    company: str

    # Cache
    cache_hit: bool
    cached_answer: Optional[ResearchAnswer]

    # Query analysis
    query_intent: Optional[QueryIntent]

    # Retrieval
    retrieved_chunks: Optional[List[RetrievedChunk]]
    sql_results: Optional[List[RetrievedChunk]]

    # Quality gates
    mnpi_blocked_chunks: Optional[List[str]]
    filtered_chunks: Optional[List[RetrievedChunk]]

    # Enrichment
    enriched_chunks: Optional[List[RetrievedChunk]]
    mosaic: Optional[MosaicCompleteness]

    # Synthesis
    answer: Optional[ResearchAnswer]
