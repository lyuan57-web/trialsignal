FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRIALSIGNAL_DB=/app/data/trialsignal.db \
    TRIALSIGNAL_MODEL=/app/models/adverse_outcome.joblib

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY data ./data
COPY models ./models
EXPOSE 8000

CMD ["uvicorn", "trialsignal.api:app", "--host", "0.0.0.0", "--port", "8000"]

