"""Arize tracing setup for the Earnings Intelligence Pipeline."""

import os

_TRACING_ENABLED = False

PROJECT_NAME = "earnings-intelligence-iteration1"


def setup_arize_tracing(project_name: str = PROJECT_NAME) -> bool:
    """Register Arize OTEL tracing and LangChain instrumentation once per process."""
    global _TRACING_ENABLED

    if _TRACING_ENABLED:
        return True

    api_key = os.getenv("ARIZE_API_KEY")
    space_id = os.getenv("ARIZE_SPACE_ID")

    if not api_key or not space_id:
        print("Arize tracing disabled: ARIZE_API_KEY and/or ARIZE_SPACE_ID not set.")
        return False

    try:
        from arize.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor
    except ImportError:
        print(
            "Arize tracing disabled: missing dependencies. "
            "Install `arize-otel` and `openinference-instrumentation-langchain`."
        )
        return False

    try:
        tracer_provider = register(
            space_id=space_id,
            api_key=api_key,
            project_name=project_name,
        )
        LangChainInstrumentor(tracer_provider=tracer_provider).instrument()
        _TRACING_ENABLED = True
        print(f"Arize tracing active → project: {project_name}")
        return True
    except Exception as exc:
        print(f"Arize tracing initialization failed: {exc}")
        return False
