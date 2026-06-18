.PHONY: test scan lint

test:
	python -m unittest discover -s tests -v

scan:
	python -m bellwether.cli scan . --fail-under 90

lint:
	ruff check bellwether
