.PHONY: build


build:
	@/home/kfluckiger/.local/bin/poetry build
install:
	@/home/kfluckiger/.local/bin/uv pip install dist/*.whl
all: build install