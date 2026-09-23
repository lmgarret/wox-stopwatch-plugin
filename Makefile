.PHONY: test lint package clean

PACKAGE := wox.plugin.stopwatch.wox

test:
	python3 -m unittest discover -s tests

lint:
	uvx ruff check wox_stopwatch tests
	uvx ruff format --check wox_stopwatch tests

package: clean
	zip -r $(PACKAGE) plugin.json wox_stopwatch -x '*__pycache__*'

clean:
	rm -f $(PACKAGE)
