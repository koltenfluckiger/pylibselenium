.PHONY: build install all smoke clean

POETRY ?= /home/kfluckiger/.local/bin/poetry
UV ?= /home/kfluckiger/.local/bin/uv
PYTHON ?= python3

# Remove previously built wheels so `uv pip install dist/*.whl` never sees two versions.
clean:
	@rm -rf dist

build: clean
	@$(POETRY) build

# `install` depends on `build`, so `make all` (and `make -j all`) always runs them in order.
install: build
	@$(UV) pip install dist/*.whl

all: install

# Headless browser smoke test against local fixtures (needs Chrome and/or Firefox installed).
smoke:
	@$(PYTHON) examples/smoke_test.py --browser chrome --browser firefox
