FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples

RUN python -m pip install --upgrade pip \
    && pip install . pytest

CMD ["uvicorn", "agentic_platform.api:app", "--host", "0.0.0.0", "--port", "8000"]
