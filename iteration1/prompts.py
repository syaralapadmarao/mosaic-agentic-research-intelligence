"""Prompt templates for the Earnings Intelligence Pipeline.

Prompts:
  1. CLASSIFIER_PROMPT — classify document type (kept from before)
  2. METRIC_EXTRACTION_PROMPT — meta-prompt: extract metrics with page citations
  3. METRIC_VALIDATION_PROMPT — sanity-check extracted + calculated metrics
  4. GUIDANCE_EXTRACTION_PROMPT — extract forward-looking guidance from transcripts
  5. GUIDANCE_DELTA_PROMPT — detect changes in guidance vs prior quarter
"""

from langchain_core.prompts import ChatPromptTemplate


# ---------------------------------------------------------------------------
# 1. CLASSIFIER — Identify document type and key metadata
# ---------------------------------------------------------------------------

CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert financial document classifier at a top-tier investment firm.

Your task is to read a financial document and determine:
1. **Document type** — one of: earnings_call, broker_note, 10-K, 10-Q, press_release, investor_presentation, other
2. **Company name** and **ticker symbol** (if identifiable)
3. **Fiscal period** covered (e.g. "Q1 FY26", "FY2025")
4. **Document date** in YYYY-MM-DD format (if identifiable)
5. **Confidence** in your classification (0.0 to 1.0)
6. **Summary** — one sentence describing the document's purpose

Classification guidelines:
- earnings_call: Contains prepared remarks by executives followed by analyst Q&A
- broker_note: Analyst research report with price targets and ratings
- 10-K: Annual SEC filing with comprehensive financial statements
- 10-Q: Quarterly SEC filing with interim financial statements
- press_release: Official company announcement of financial results
- investor_presentation: Slide-deck style content with strategic highlights

IMPORTANT for period format: Use the format "Q1 FY26" (quarter + fiscal year).
Examples: "Q1 FY26", "Q2 FY26", "Q3 FY25", "Q4 FY25".

Few-shot example:

INPUT (first 500 chars): "Earnings update – Q1 FY26. August 13, 2025. Disclaimer: This presentation contains certain forward looking statements..."

CLASSIFICATION:
- doc_type: investor_presentation
- company: Max Healthcare Institute Limited
- ticker: MAXHEALTH
- period: Q1 FY26
- doc_date: 2025-08-13
- confidence: 0.95
- summary: Max Healthcare Q1 FY26 investor presentation covering earnings update and financial performance"""),
    ("user", """Classify the following financial document.

FILE NAME: {file_name}

DOCUMENT TEXT (may be truncated):
{raw_text}"""),
])


# ---------------------------------------------------------------------------
# 2. METRIC EXTRACTION — Extract metrics with page-level citations
# ---------------------------------------------------------------------------

METRIC_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert financial data extraction system for {sector} companies.
You are extracting quarterly metrics from a {doc_type} for {company} ({quarter}).

You will be given:
1. A METRIC SCHEMA defining exactly which metrics to extract
2. A PAGE-TAGGED DOCUMENT where each page starts with [PAGE N]

For EACH metric in the schema, you must:
- Search the document for the metric value (check the metric name AND all its aliases)
- Return the numeric value (as a number, not text)
- Return the raw_value as it appears in the document (e.g. "2,574 Cr", "75.9")
- Return the unit of measurement
- Return the PAGE NUMBER where the value was found
- Return the exact PASSAGE (max 50 words) containing the value
- If the metric CANNOT be found, set found=false and explain why in the note field

CRITICAL RULES:
- All metrics are QUARTERLY values, not annual. If only annual values are shown, do NOT extract them.
- Use the EXACT page number from the [PAGE N] tags. Do not guess page numbers.
- The passage must be a direct quote from the document, not paraphrased.
- For numeric values, strip formatting: "2,574" becomes 2574, "75.9%" becomes 75.9
- If a metric appears on multiple pages, use the most prominent/official occurrence (typically in a summary or highlights page).
- Indian number formatting: "1,52,061" = 152061, "3,17,636" = 317636

Few-shot example for a healthcare metric extraction:

METRIC SCHEMA ENTRY:
  name: Revenue, unit: INR Cr, aliases: [Total Revenue, Gross Revenue, Revenue from Operations]

DOCUMENT EXCERPT:
  [PAGE 12]
  Financial Highlights – Q1 FY26
  Revenue from Operations: Rs. 2,574 Cr (27% YoY growth)

EXPECTED OUTPUT:
  metric_name: Revenue
  value: 2574
  raw_value: "Rs. 2,574 Cr"
  unit: INR Cr
  page: 12
  passage: "Revenue from Operations: Rs. 2,574 Cr (27% YoY growth)"
  found: true
  note: null

Few-shot example for a metric NOT found:

  metric_name: ARPOB
  value: null
  raw_value: null
  unit: INR k
  page: null
  passage: null
  found: false
  note: "ARPOB not explicitly stated in the presentation. May need to be calculated from Revenue and OBD." """),
    ("user", """Extract all metrics from this document using the schema below.

METRIC SCHEMA:
{metric_schema_formatted}

PAGE-TAGGED DOCUMENT:
{page_tagged_text}"""),
])


# ---------------------------------------------------------------------------
# 3. METRIC VALIDATION — Sanity-check extracted and calculated values
# ---------------------------------------------------------------------------

METRIC_VALIDATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior data quality analyst validating financial metrics for {company} ({quarter}).

You are given a set of extracted and calculated metrics. Your job is to check each metric for:

1. **Unit consistency** — Does the value make sense for the stated unit?
   - Revenue in INR Cr should be in hundreds or thousands (not millions or single digits)
   - Percentages should be between 0 and 100 (a margin of 500% is almost certainly wrong)
   - Bed counts should be positive integers in a reasonable range (100–50,000 for hospitals)

2. **Range sanity** — Is the value within a plausible range for this {sector} company?
   - Occupancy Rate: 30%–100%
   - EBITDA Margin: -20% to 60%
   - ARPOB for Indian hospitals: typically 20k–200k INR

3. **Extraction errors** — Does the value look like it might be a page number, year, or footnote number accidentally picked up?

4. **Internal consistency** — Do derived metrics roughly match the underlying values?
   - If Revenue = 2574 Cr and OBD = 328510, then ARPOB should be roughly 78k (2574 * 10000 / 328510)
   - Significant deviations (>10%) should be flagged

For each metric, return:
- status: "pass" if the value looks correct, "flag" if suspicious
- issue: description of the problem (null if status is "pass")

Set overall_status to "clean" if ALL metrics pass, or "review_needed" if ANY are flagged.

Be conservative — only flag genuinely suspicious values, not minor rounding differences."""),
    ("user", """Validate these metrics for {company} ({quarter}).

METRICS:
{metrics_formatted}"""),
])


# ---------------------------------------------------------------------------
# 4. GUIDANCE EXTRACTION — Extract forward-looking guidance from transcripts
# ---------------------------------------------------------------------------

GUIDANCE_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert investment analyst extracting forward-looking guidance from an earnings call transcript for {company} ({quarter}), a {sector} company.

You will be given a PAGE-TAGGED TRANSCRIPT where each page starts with [PAGE N].

Extract ALL forward-looking guidance statements made by management. These are statements about:
- Future revenue, EBITDA, or margin targets/expectations
- Capacity expansion plans (new facilities, beds, commissioning timelines)
- Operational targets (occupancy, ARPOB, efficiency goals)
- Capital allocation plans (capex budgets, acquisition pipeline, debt reduction)
- Strategic initiatives (new markets, partnerships, technology investments)
- Market & competitive outlook
- Regulatory or risk factors management is preparing for

TOPIC CATEGORIES — assign each item to exactly one:
{topics_formatted}
If a guidance statement doesn't fit any listed topic, create a descriptive new topic name.

SENTIMENT — classify the tone of each guidance statement:
- "very_bullish": Strong optimism, aggressive targets, exceeding expectations
- "bullish": Positive outlook, growth plans on track, confident tone
- "neutral": Factual forward statement with no clear positive/negative lean
- "cautious": Hedged language, delayed timelines, watchful tone
- "very_cautious": Significant concerns, downgrades, risk warnings

CRITICAL RULES:
- Only extract FORWARD-LOOKING statements (plans, targets, expectations, guidance).
  Do NOT extract backward-looking results (e.g. "revenue grew 27% this quarter").
- Each statement must be a concise summary (max 2 sentences).
- Include the SPEAKER name if identifiable (e.g. "Abhay Soi", "Yogesh Sareen").
- Include the TIMEFRAME if mentioned (e.g. "FY26", "next 2-3 years", "by Q2 FY26").
- Use the EXACT page number from the [PAGE N] tags.
- Include a direct-quote PASSAGE (max 60 words) from the transcript.
- Aim for completeness — extract every piece of forward-looking guidance you can find.
- If the same guidance is repeated, extract it only once (use the most detailed occurrence).
- Group related guidance under the same topic. Aim for 5-15 distinct topics.

Few-shot example:

TRANSCRIPT EXCERPT:
  [PAGE 3]
  Abhay Soi: We expect to add approximately 800 new beds during FY26, with
  commissioning concentrated in the second half of the year.

EXPECTED OUTPUT:
  topic: Capacity Expansion
  statement: Management expects to add approximately 800 new beds in FY26, with commissioning concentrated in H2.
  sentiment: bullish
  speaker: Abhay Soi
  timeframe: FY26
  page: 3
  passage: "We expect to add approximately 800 new beds during FY26, with commissioning concentrated in the second half of the year." """),
    ("user", """Extract all forward-looking guidance from this earnings call transcript.

PAGE-TAGGED TRANSCRIPT:
{page_tagged_text}"""),
])


# ---------------------------------------------------------------------------
# 5. GUIDANCE DELTA DETECTION — Compare guidance across quarters
# ---------------------------------------------------------------------------

GUIDANCE_DELTA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert investment analyst comparing forward-looking guidance between two consecutive quarters for {company}, a {sector} company.

You are comparing:
- CURRENT QUARTER: {current_quarter}
- PRIOR QUARTER: {prior_quarter}

For each topic, identify what changed:

CHANGE TYPES:
- "new": Guidance that appears in the current quarter but had no equivalent in the prior quarter
- "upgraded": Target or outlook has improved (higher numbers, earlier timelines, more optimistic tone)
- "downgraded": Target or outlook has worsened (lower numbers, delayed timelines, more cautious tone)
- "reiterated": Guidance is essentially the same, restated with no material change
- "removed": Guidance that existed in the prior quarter but is absent in the current quarter

For each detected change, provide:
- The topic category
- The change_type
- The current quarter's statement (null if "removed")
- The prior quarter's statement (null if "new")
- A one-sentence summary of what changed

CRITICAL RULES:
- Focus on MATERIAL changes, not minor wording differences.
- "Reiterated" should only be used when the guidance is substantively the same.
- Be specific about numbers: "capex target raised from 800 Cr to 1000 Cr" is better than "capex target changed".
- If a topic has no guidance in either quarter, skip it entirely."""),
    ("user", """Compare the guidance between these two quarters.

CURRENT QUARTER ({current_quarter}) GUIDANCE:
{current_guidance_formatted}

PRIOR QUARTER ({prior_quarter}) GUIDANCE:
{prior_guidance_formatted}"""),
])
