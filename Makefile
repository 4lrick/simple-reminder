.PHONY: venv install test run

venv:
	python -m venv .venv

install: venv
	source .venv/bin/activate && pip install -r requirements.txt

test: install
	# set discord token environment variable
	 source .venv/bin/activate && python -m pytest tests/ -v

run: install
	# set discord token environment variable
	source .venv/bin/activate && python simple_reminder.py
