.PHONY: venv install test run

venv:
	python -m venv .venv

install: venv
	source .venv/bin/activate && python -m pip install --upgrade pip && pip install -r requirements.txt

test: install
	source .venv/bin/activate && python -m pytest tests/ -v

run: install
	source .venv/bin/activate && python simple_reminder.py

