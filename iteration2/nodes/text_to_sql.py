"""Text-to-SQL Node — Query iteration1 structured stores + financial API.

For STRUCTURED or HYBRID intent, converts the query to SQL against:
  - metrics table (iteration1): actuals
  - guidance table (iteration1): management guidance
  - analyst_estimates table (iteration2): sell-side estimates
  - visit_insights table (iteration2): field observations

On SQL failure, falls back to vector retrieval context.
"""

import re

from langchain_core.prompts import ChatPromptTemplate

from iteration2.state import OnlinePipelineState, RetrievedChunk
from iteration2 import storage as iter2_storage
import iteration1.storage as iter1_storage


SQL_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert SQL analyst for an investment research database.

Generate a SQLite query for the analyst's question about {company}.

Available tables:

1. **metrics** (from company earnings):
   - company TEXT, quarter TEXT, metric_name TEXT, reported_value REAL,
     calculated_value REAL, unit TEXT, yoy_change REAL, qoq_change REAL

2. **guidance** (management forward guidance):
   - company TEXT, quarter TEXT, topic TEXT, current_guidance TEXT,
     prior_guidance TEXT, direction TEXT (raised/maintained/lowered/new)

3. **analyst_estimates** (sell-side forward estimates):
   - company TEXT, metric_name TEXT, value REAL, unit TEXT, period TEXT,
     analyst TEXT, firm TEXT

4. **visit_insights** (field intelligence):
   - company TEXT, topic TEXT, observation TEXT, sentiment TEXT,
     conviction TEXT, source_person TEXT, date TEXT

RULES:
- Return ONLY the SQL query, nothing else
- Use LIKE for fuzzy text matching
- Always filter by company='{company}'
- For time-based queries, use the quarter or period columns
- Limit results to 25 rows
- If unsure, query from metrics or guidance first"""),
    ("user", "Question: {query}"),
])


def text_to_sql(state: OnlinePipelineState, llm) -> dict:
    """LangGraph node: convert query to SQL and execute against SQLite."""
    if state.get("cache_hit"):
        return {}

    intent = state.get("query_intent")
    if not intent:
        return {}

    if intent.intent == "UNSTRUCTURED":
        return {}

    company = state["company"]

    chain = SQL_GENERATION_PROMPT | llm
    result = chain.invoke({
        "company": company,
        "query": state["query"],
    })

    sql_text = result.content.strip()
    sql_text = sql_text.replace("```sql", "").replace("```", "").strip()

    conn = iter2_storage.get_connection(company)

    try:
        cursor = conn.execute(sql_text)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()

        sql_chunks = []
        for row in rows[:25]:
            row_dict = dict(zip(columns, row)) if isinstance(row, tuple) else dict(row)
            text_parts = [f"{k}: {v}" for k, v in row_dict.items() if v is not None]
            text = " | ".join(text_parts)

            sql_chunks.append(RetrievedChunk(
                text=text,
                source_type="disclosure",
                doc_type="structured_data",
                company=company,
                file_name="sqlite_query",
                section=f"SQL: {sql_text[:100]}",
                relevance_score=0.95,
            ))

        return {"sql_results": sql_chunks}

    except Exception as e:
        return {"sql_results": [RetrievedChunk(
            text=f"SQL query failed: {str(e)}. Falling back to vector retrieval.",
            source_type="disclosure",
            doc_type="sql_error",
            company=company,
            file_name="sql_fallback",
            relevance_score=0.0,
        )]}

    finally:
        conn.close()
