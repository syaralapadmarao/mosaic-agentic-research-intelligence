"""LLM Judge (subjective) evaluation functions for Iteration 1.

5 eval metrics using phoenix.evals.create_classifier with GOOD/PARTIAL/BAD rubrics:
  1. taxonomy_quality               — topics MECE, business-relevant, right granularity
  2. guidance_extraction_completeness — captures key points, targets, speakers, sentiment
  3. delta_detection_accuracy        — changes are real and material, not rephrasings
  4. taxonomy_evolution_quality      — new topics genuine, backfill accurate, drops flagged
  5. cross_quarter_comparison_quality — surfaces trajectory insights, not just juxtaposition

Each evaluator follows the Arize pattern:
  - create_classifier(name, llm, prompt_template, choices)
  - classifier.evaluate({...variables...}) → [ClassificationResult]
"""

from phoenix.evals import create_classifier

JUDGE_CHOICES = {"GOOD": 1.0, "PARTIAL": 0.5, "BAD": 0.0}


# ---------------------------------------------------------------------------
# 1. Taxonomy Quality
# ---------------------------------------------------------------------------

TAXONOMY_QUALITY_PROMPT = """You are an investment analyst evaluating the quality of a topic taxonomy
extracted from an earnings call transcript.

COMPANY: {company}
SECTOR: {sector}

EXTRACTED TOPICS:
{topics_list}

TRANSCRIPT EXCERPT (first 3000 chars):
{transcript_excerpt}

RUBRIC:
- GOOD: Topics are business-relevant (an analyst would track them), mutually exclusive (no overlap),
  collectively exhaustive (covers key themes), and at appropriate granularity (8-15 topics).
  Example: IndiGo taxonomy includes "Fleet Expansion", "Route Network", "Yield Management",
  "Cost Structure (CASK)", "International Operations", "Competitive Positioning",
  "Regulatory Environment", "Sustainability / SAF" - 8 topics, each distinct and analytically useful.

- PARTIAL: Topics are relevant but either overlap significantly, miss a major theme discussed
  at length, or are too granular (>20 topics splitting related concepts).
  Example: "Fleet Expansion" and "Aircraft Orders" as separate topics (overlap - orders are a
  subset of fleet expansion). Or: missing "International Operations" entirely despite 3 pages
  of discussion on it.

- BAD: Topics include irrelevant items, are too abstract to be analytically useful, or miss
  >30% of substantive discussion topics.
  Example: Includes "Pleasantries", "Operator Instructions", "Thank You Remarks". Or uses only
  "Business Overview" and "Financial Performance" - too abstract for an analyst to track anything specific.

Your response must be a single word: GOOD, PARTIAL, or BAD."""


# ---------------------------------------------------------------------------
# 2. Guidance Extraction Completeness
# ---------------------------------------------------------------------------

GUIDANCE_COMPLETENESS_PROMPT = """You are an investment analyst evaluating whether guidance extraction
from an earnings call transcript is complete and accurate.

COMPANY: {company}
QUARTER: {quarter}
TOPIC: {topic}

EXTRACTED GUIDANCE:
{extracted_guidance}

SOURCE TRANSCRIPT PASSAGE:
{transcript_passage}

RUBRIC:
- GOOD: Captures the primary guidance statement, any quantitative targets, correct speaker
  attribution, and sentiment - consistent with what a human analyst would note.
  Example: Topic "Fleet Expansion" - extracts "Accelerating to 40 aircraft/year, widebody order
  confirmed for 2026 delivery" attributed to CEO, page 8. Sentiment: Very Bullish.

- PARTIAL: Captures directional guidance but misses quantitative specifics, or attributes to
  wrong speaker.
  Example: Notes "bullish on fleet expansion" but misses the specific "40 aircraft/year" target
  and the widebody order detail. Or attributes the guidance to the CFO instead of the CEO.

- BAD: Misses the core guidance entirely, extracts tangential commentary as the main point, or
  hallucinates guidance not present in the transcript.
  Example: Extracts an analyst's question about fleet age as the guidance, missing management's
  actual answer entirely. Or states "management guided 50 aircraft/year" when no such number
  appears in the transcript.

Your response must be a single word: GOOD, PARTIAL, or BAD."""


# ---------------------------------------------------------------------------
# 3. Delta Detection Accuracy
# ---------------------------------------------------------------------------

DELTA_DETECTION_PROMPT = """You are an investment analyst evaluating whether a detected quarter-over-quarter
guidance change is real, material, and correctly characterized.

COMPANY: {company}
CURRENT QUARTER: {current_quarter}
PRIOR QUARTER: {prior_quarter}
TOPIC: {topic}

DETECTED DELTA:
  Change type: {change_type}
  Current guidance: {current_statement}
  Prior guidance: {prior_statement}
  Summary: {delta_summary}

RUBRIC:
- GOOD: Correctly identifies direction change, specific revision (prior vs. current target), and
  the change is genuinely material - not a rephrasing of the same stance.
  Example: Flags "EBITDAR Margin guidance revised down: Q3 guided 18-20%, Q4 now guiding 15-17%
  citing fuel cost headwinds." Direction: Bullish → Cautious. Material: Yes (300bps revision).

- PARTIAL: Identifies a real change but overstates/understates its significance, or flags a
  stylistic rephrasing as a substantive shift.
  Example: Flags a delta because Q3 said "we expect strong margins" and Q4 said "margins remain
  healthy" - a rephrasing, not a substantive change.

- BAD: Flags a delta that doesn't exist (hallucinated), misses a clear direction reversal, or
  conflates silence with a negative signal when the topic simply was not asked about.
  Example: Reports "management turned cautious on fleet expansion" when Q4 transcript simply
  had no analyst question on the topic - silence ≠ negative signal.

Your response must be a single word: GOOD, PARTIAL, or BAD."""


# ---------------------------------------------------------------------------
# 4. Taxonomy Evolution Quality
# ---------------------------------------------------------------------------

TAXONOMY_EVOLUTION_PROMPT = """You are an investment analyst evaluating how well the system handles
taxonomy evolution between two consecutive quarters.

COMPANY: {company}
PRIOR QUARTER: {prior_quarter}  →  CURRENT QUARTER: {current_quarter}

PRIOR QUARTER TOPICS:
{prior_topics}

CURRENT QUARTER TOPICS:
{current_topics}

NEW TOPICS ADDED: {new_topics}
TOPICS DROPPED: {dropped_topics}

RUBRIC:
- GOOD: Correctly identifies genuinely new topics (not renamings of existing ones), backfill
  extraction returns accurate historical data, and dropped topics are flagged when truly absent.
  Example: Q4 introduces "Widebody Operations" as new topic (first widebody order). System adds
  it to taxonomy, correctly returns "Not discussed" for prior quarters. Does NOT merge it into
  existing "Fleet Expansion."

- PARTIAL: Identifies new topics but some are variants of existing ones; or flags a topic as
  dropped when it was discussed under a different name.
  Example: Creates "Widebody Strategy" as new AND keeps it under "Fleet Expansion" - duplication.
  Or: backfill finds a Q2 mention that was actually a passing comment in a different context.

- BAD: Misses genuinely new topics, creates redundant taxonomy entries, or backfill produces
  hallucinated historical data.
  Example: Fails to detect widebody discussion entirely. Or: backfill "finds" references in Q1
  transcript that do not exist - hallucinated historical data.

Your response must be a single word: GOOD, PARTIAL, or BAD."""


# ---------------------------------------------------------------------------
# 5. Cross-Quarter Comparison Quality
# ---------------------------------------------------------------------------

CROSS_QUARTER_PROMPT = """You are an investment analyst evaluating the quality of a cross-quarter
comparison of management guidance on a specific topic.

COMPANY: {company}
TOPIC: {topic}
QUARTERS COMPARED: {quarters_compared}

GUIDANCE BY QUARTER:
{guidance_by_quarter}

COMPARISON/SYNTHESIS:
{comparison_text}

RUBRIC:
- GOOD: The comparison surfaces genuine analytical insight - trajectory shifts, inflection points,
  accelerating/decelerating trends - beyond what is visible from reading any single quarter.
  Connects dots across quarters that an analyst would value.
  Example: "Fleet Expansion" across Q1-Q4 FY24 - comparison notes: "Guidance accelerated
  progressively: Q1 guided 30 aircraft/year, Q2 revised to 35, Q4 jumped to 40 with widebody
  confirmation. This marks a shift from organic growth to a step-change in fleet strategy."

- PARTIAL: Accurately presents each quarter's information but merely juxtaposes them without
  synthesizing a trajectory or drawing analytical connections. Correct but not insightful.
  Example: "Q1 guided 30 aircraft/year. Q2 guided 35 aircraft/year. Q3 guided 35 aircraft/year.
  Q4 guided 40 aircraft/year with widebody order." - Lists each quarter accurately but doesn't
  note the acceleration pattern or strategic significance.

- BAD: Restates a single quarter's guidance as the comparison, ignores available multi-quarter
  context, fabricates a trend not supported by the data, or presents a flat trajectory as if
  it were changing.
  Example: States "management has consistently guided aggressive fleet expansion" when Q1-Q2
  were actually conservative (30-35) and only Q4 marked a real shift.

Your response must be a single word: GOOD, PARTIAL, or BAD."""


# ---------------------------------------------------------------------------
# Builder Functions
# ---------------------------------------------------------------------------

def build_taxonomy_quality_evaluator(eval_llm):
    """Build the taxonomy quality LLM judge using create_classifier."""
    return create_classifier(
        name="taxonomy_quality",
        llm=eval_llm,
        prompt_template=TAXONOMY_QUALITY_PROMPT,
        choices=JUDGE_CHOICES,
    )


def build_guidance_completeness_evaluator(eval_llm):
    """Build the guidance extraction completeness LLM judge."""
    return create_classifier(
        name="guidance_completeness",
        llm=eval_llm,
        prompt_template=GUIDANCE_COMPLETENESS_PROMPT,
        choices=JUDGE_CHOICES,
    )


def build_delta_detection_evaluator(eval_llm):
    """Build the delta detection accuracy LLM judge."""
    return create_classifier(
        name="delta_detection",
        llm=eval_llm,
        prompt_template=DELTA_DETECTION_PROMPT,
        choices=JUDGE_CHOICES,
    )


def build_taxonomy_evolution_evaluator(eval_llm):
    """Build the taxonomy evolution quality LLM judge."""
    return create_classifier(
        name="taxonomy_evolution",
        llm=eval_llm,
        prompt_template=TAXONOMY_EVOLUTION_PROMPT,
        choices=JUDGE_CHOICES,
    )


def build_cross_quarter_evaluator(eval_llm):
    """Build the cross-quarter comparison quality LLM judge."""
    return create_classifier(
        name="cross_quarter_comparison",
        llm=eval_llm,
        prompt_template=CROSS_QUARTER_PROMPT,
        choices=JUDGE_CHOICES,
    )
