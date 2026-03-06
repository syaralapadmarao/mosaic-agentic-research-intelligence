# Iteration 1: Earnings Intelligence Dashboard

A LangGraph pipeline that processes earnings call transcripts and investor presentations, extracting structured metrics and forward-looking guidance into a rolling 8-quarter dashboard.

## Architecture

Two parallel workflows triggered by document classification:

- **Workflow A** (Presentation → Metrics): Extract → Calculate derived metrics → Validate → Assemble rolling table
- **Workflow B** (Transcript → Guidance): Extract topics + sentiment → Detect Q-o-Q deltas → Assemble guidance tracker

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API key

### 1. Backend

```bash
# From the repo root
cp .env.example .env  # Add your OPENAI_API_KEY (and optionally ARIZE_API_KEY, ARIZE_SPACE_ID)

# Install Python deps (use your project's venv)
pip install fastapi uvicorn langchain langchain-openai langchain-community pypdf pydantic

# Start the API server
cd mosaic-agentic-research-intelligence
python -m uvicorn iteration1.api:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend

```bash
cd iteration1/frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

### 3. Using the Dashboard

1. Select a **Schema** from the sidebar dropdown (e.g., `hospital`)
2. Click a **Company** from the sidebar
3. Click **Run Pipeline** in the bottom status bar
4. Watch the progress bar as PDFs are processed
5. Switch between **Metrics Tracker** and **Guidance Tracker** tabs

## Project Structure

```
iteration1/
├── api.py                  # FastAPI backend
├── app.py                  # Gradio UI (legacy)
├── main.py                 # CLI entry point
├── pipeline.py             # LangGraph pipeline definition
├── state.py                # Pydantic models + pipeline state
├── storage.py              # SQLite persistence layer
├── prompts.py              # LLM prompt templates
├── pdf_parser.py           # PDF → page-tagged text
├── tracing.py              # Arize tracing setup
├── nodes/                  # LangGraph nodes
│   ├── classifier.py       # Document type classifier
│   ├── metric_extractor.py # LLM metric extraction
│   ├── metric_calculator.py# Derived metric formulas
│   ├── metric_validator.py # LLM validation checks
│   ├── metric_assembler.py # Rolling table assembly
│   ├── guidance_extractor.py # LLM guidance extraction
│   ├── guidance_delta.py   # Q-o-Q change detection
│   └── guidance_assembler.py # Guidance table assembly
├── schemas/                # Industry metric schemas
│   └── hospital.json
├── evals/                  # Evaluation framework
│   ├── code_evals.py       # 5 code-based evals
│   ├── llm_judge_evals.py  # 5 LLM judge evals
│   ├── arize_experiment.py # Arize experiment runner
│   ├── runner.py           # CLI eval runner
│   └── ground_truth/       # Ground truth templates
├── frontend/               # React + Vite + Tailwind
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   └── components/
│   │       ├── Sidebar.jsx
│   │       ├── MetricsTable.jsx
│   │       ├── GuidanceTracker.jsx
│   │       └── StatusBar.jsx
│   └── package.json
├── sample_docs/            # PDF files (not in git)
└── data/                   # SQLite databases (not in git)
```

## Running Evals

```bash
# Code-based evals (ground-truth-free)
python -m iteration1.evals.runner --suite code

# LLM judge evals
python -m iteration1.evals.runner --suite judge

# Both suites
python -m iteration1.evals.runner --suite all

# Upload to Arize
python -m iteration1.evals.runner --suite all --arize
```

## Sample Docs

Place PDF files under `iteration1/sample_docs/{company}/`:

```
sample_docs/
├── max/
│   ├── Q1_FY26_presentation.pdf
│   └── transcript/
│       └── Q1_FY26_transcript.pdf
├── apollo/
│   ├── Q2_FY26_presentation.pdf
│   └── transcript/
│       └── Q2_FY26_transcript.pdf
└── ...
```

PDFs are not checked into git due to size. Quarter is inferred from the filename (e.g., `Q1FY26`, `Q3_FY_25`).
