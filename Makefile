.PHONY: test lint ingest demo quality train report api clean

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src tests

ingest:
	.venv/bin/python -m trialsignal.pipeline --condition "non-small cell lung cancer" --max-studies 100

demo:
	.venv/bin/python -m trialsignal.pipeline --fixture tests/fixtures/studies_response.json

quality:
	.venv/bin/python -m trialsignal.data_quality --database data/trialsignal.db

train:
	.venv/bin/python -m trialsignal.risk_model --database data/trialsignal.db

report:
	.venv/bin/python -m trialsignal.validation_report

api:
	TRIALSIGNAL_DB=data/trialsignal.db .venv/bin/uvicorn trialsignal.api:app --reload

clean:
	python3 -c 'from pathlib import Path; p=Path("data/trialsignal.db"); p.unlink(missing_ok=True)'

