.PHONY: test lint-check format

test:
	python3 -m unittest -q

lint-check:
	python3 -m py_compile temps.py test_temps.py

format:
	@echo "rewrites the files in place"
