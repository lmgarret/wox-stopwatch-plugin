.PHONY: test lint package clean

PACKAGE := wox.plugin.stopwatch.wox

test:
	uv run python -m unittest discover -s tests

lint:
	uv run ruff check wox_stopwatch tests
	uv run ruff format --check wox_stopwatch tests

package: clean
	zip -r $(PACKAGE) plugin.json images wox_stopwatch -x '*__pycache__*'

clean:
	rm -f $(PACKAGE)
