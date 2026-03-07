# Iteration 2: Multi-Source Research Assistant

**Workflow Agent + RAG + Tools — Pull (Query) Mode**  
Medium Control · Medium Agency

## Overview

Iteration 2 extends the Iteration 1 Earnings Intelligence Dashboard with multi-source document ingestion, RAG-based retrieval, consensus divergence detection, and source attribution. It processes five document types across three namespaces (Disclosure, Opinion, Field Data), implementing the "Mosaic Theory" approach where investment insights are assembled from complementary information sources.

## Architecture

### Two Pipelines

```
OFFLINE (Document Ingestion)
  Parse → MNPI Gate → Classify → Route:
    Workflow A: Presentations → Metrics (reused from iter1)
    Workflow B: Transcripts → Guidance (reused from iter1)
    Workflow C: Sell-Side Reports → Ratings + Estimates
    Workflow D: Visit Notes → Insights + Signals
  → Smart Chunk → Metadata Tag → Embed into ChromaDB

ONLINE (Research Query)
  Cache Check → Query Analyzer → Retrieve + Text-to-SQL
  → MNPI 2nd Screen → Corrective RAG
  → Enrich Context → Synthesize → Divergence Detection
  → Cache Store → Return Answer
```

### Three Namespaces (ChromaDB)

| Namespace | Sources | Character | Freshness |
|-----------|---------|-----------|-----------|
| DISCLOSURE | Transcripts, Presentations | Authoritative, lagging | 90 days |
| OPINION | Sell-side reports, Broker emails | Forward-looking, biased | 60 days |
| FIELD_DATA | Visit notes, Channel checks | Highest alpha, highest risk | 90 days |

### Key Components

- **MNPI Gate**: Regex/keyword pre-ingestion screening with PII scrubbing
- **Smart Chunker**: Source-type-aware chunking (400-1200 chars depending on doc type)
- **3-Namespace ChromaDB**: OpenAI `text-embedding-3-small` embeddings, cosine similarity
- **Query Analyzer**: LLM-based intent classification (STRUCTURED/UNSTRUCTURED/HYBRID)
- **Text-to-SQL**: Queries iteration1 structured data + iteration2 analyst estimates
- **Financial API (MCP Stub)**: Mock live prices, consensus estimates, peer comparison
- **Corrective RAG**: LLM judges chunk relevance (RELEVANT/TANGENTIAL/IRRELEVANT)
- **Consensus Divergence Detection**: Surfaces sell-side disagreements
- **Mosaic Completeness**: Tracks 3-namespace coverage per answer
- **Semantic Cache**: Exact query match for repeated questions

## Directory Structure

```
iteration2/
├── __init__.py
├── api.py                  # FastAPI backend (27 endpoints)
├── chunker.py              # Source-type-aware document chunking
├── financial_api.py        # MCP stub for mock prices/estimates
├── md_parser.py            # Markdown parser with section tagging
├── mnpi_gate.py            # MNPI detection + PII scrubbing
├── online_pipeline.py      # LangGraph online research pipeline
├── pipeline.py             # LangGraph offline ingestion pipeline
├── prompts.py              # All LLM prompt templates
├── state.py                # Pydantic models + pipeline state
├── storage.py              # Extended SQLite storage
├── vector_store.py         # 3-namespace ChromaDB wrapper
├── nodes/
│   ├── classifier.py       # Extended document classifier
│   ├── metadata_tagger.py  # Deterministic chunk metadata tagging
│   ├── quality_gates.py    # MNPI 2nd screen + corrective RAG
│   ├── query_analyzer.py   # Cache check + LLM query analysis
│   ├── retriever.py        # Multi-namespace semantic search
│   ├── sell_side_extractor.py  # Workflow C: sell-side reports
│   ├── synthesizer.py      # Enrichment + synthesis + divergence
│   ├── table_extractor.py  # Financial table parser
│   ├── text_to_sql.py      # Text-to-SQL node
│   └── visit_note_extractor.py  # Workflow D: visit notes
├── evals/
│   ├── code_evals.py       # 8 code-based evaluation functions
│   ├── runner.py           # CLI eval runner
│   └── ground_truth/
│       └── mnpi_test_docs.json
├── sample_docs/
│   ├── max/
│   │   ├── sell_side/      # Sell-side analyst reports (.md)
│   │   ├── visit_notes/    # Site visit and channel check notes (.md)
│   │   └── broker_emails/  # Analyst emails (.md)
│   ├── apollo/
│   │   ├── sell_side/
│   │   ├── visit_notes/
│   │   └── broker_emails/
│   └── rainbow/
│       ├── sell_side/
│       ├── visit_notes/
│       └── broker_emails/
└── frontend/
    └── src/
        ├── App.jsx             # Main app with tabs
        ├── api.js              # API client
        └── components/
            ├── ConsensusView.jsx    # Consensus estimates table
            ├── DivergenceAlert.jsx  # Divergence alert cards
            ├── IngestPanel.jsx      # Document ingestion UI
            ├── MosaicBanner.jsx     # 3-namespace completeness bar
            ├── ResearchChat.jsx     # Chat-based research interface
            ├── Sidebar.jsx          # Company selector + stats
            ├── SourceBadges.jsx     # Inline source attribution
            └── SourcesPanel.jsx     # Ingested sources + MNPI audit
```

## Running

### Prerequisites

```bash
# From the project root
source .venv/bin/activate
export OPENAI_API_KEY=sk-...
```

### Backend

```bash
cd mosaic-agentic-research-intelligence
uvicorn iteration2.api:app --reload --port 8002
```

### Frontend

```bash
cd mosaic-agentic-research-intelligence/iteration2/frontend
npm install
npm run dev
```

Open http://localhost:5174

### Workflow

1. Select a company in the sidebar
2. Go to **Ingest** tab → click "Start Ingestion" to process all documents
3. Switch to **Research** tab → ask questions in the chat
4. Check **Consensus** tab for analyst estimate aggregation
5. Check **Sources** tab for ingested documents and MNPI audit log

### Run Evaluations

```bash
python -m iteration2.evals.runner --eval all
```

## API Endpoints

### Research
- `POST /api/research/query` — Run research pipeline
- `POST /api/research/ingest` — Ingest documents
- `GET /api/research/ingest/status/{company}` — Poll ingestion
- `GET /api/research/sources/{company}` — List sources
- `GET /api/research/consensus/{company}` — Consensus estimates
- `GET /api/research/insights/{company}` — Visit note insights
- `GET /api/research/divergences/{company}` — Divergences
- `GET /api/research/cache/{company}` — Cache stats
- `GET /api/research/mnpi-audit` — MNPI audit log
- `GET /api/research/stats/{company}` — Vector store stats

### Financial API (MCP Stub)
- `GET /api/finance/price/{company}` — Mock live price
- `GET /api/finance/consensus/{company}` — Mock consensus
- `GET /api/finance/peers/{company}` — Mock peer comparison

### Iteration 1 (re-exported)
- `GET /api/companies`, `GET /api/metrics/{company}`, etc.

## Evaluation Results

| Eval | Score |
|------|-------|
| MNPI Gate Accuracy | 100% (8/8) |
| Source Attribution Coverage | 1.0 |
| Mosaic Completeness | 100% |

## Design Simplifications (Demo vs Production)

| Component | Production | Demo |
|-----------|-----------|------|
| Embeddings | mE5-large (local) | OpenAI text-embedding-3-small |
| Search | BM25 hybrid + cross-encoder re-rank | Pure semantic search |
| MNPI Gate | Full LLM classifier | Keyword/regex |
| Semantic Cache | Embedding similarity | Exact query string match |
| Financial API | Real market data MCP | Mock data stub |
