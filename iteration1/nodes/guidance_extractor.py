"""LLM Extract node — extracts forward-looking guidance from earnings call transcripts."""

from iteration1.state import PipelineState, GuidanceExtractionResult, GUIDANCE_TOPICS
from iteration1.prompts import GUIDANCE_EXTRACTION_PROMPT


def extract_guidance(state: PipelineState, llm) -> dict:
    """LangGraph node: extract forward-looking guidance from a transcript.

    Reads the page-tagged transcript text and uses the LLM to identify
    all forward-looking statements, categorized by topic.

    Returns the 'guidance_items' key for PipelineState.
    """
    classification = state["classification"]
    company = state.get("company") or classification.company
    schema = state.get("metric_schema")
    sector = schema.sector if schema else "Financial"

    topics_formatted = "\n".join(f"- {t}" for t in GUIDANCE_TOPICS)

    structured_llm = llm.with_structured_output(GuidanceExtractionResult)
    chain = GUIDANCE_EXTRACTION_PROMPT | structured_llm

    result = chain.invoke({
        "company": company,
        "quarter": state["quarter"],
        "sector": sector,
        "topics_formatted": topics_formatted,
        "page_tagged_text": state["page_tagged_text"],
    })

    by_topic = {}
    for item in result.items:
        by_topic.setdefault(item.topic, []).append(item)

    print(f"[GuidanceExtractor] {company} ({state['quarter']}) | "
          f"found {len(result.items)} guidance items across {len(by_topic)} topics")
    for topic, items in by_topic.items():
        print(f"  {topic}: {len(items)} items")
        for item in items:
            speaker = f" [{item.speaker}]" if item.speaker else ""
            timeframe = f" ({item.timeframe})" if item.timeframe else ""
            print(f"    • {item.statement[:80]}...{speaker}{timeframe} (p.{item.page})")

    return {"guidance_items": result.items}
