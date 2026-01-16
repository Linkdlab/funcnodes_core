# Contributing to funcnodes-core

This repository contains the **core runtime** (nodes, IO, nodespace, library, config, serialization).

## Development setup (Python)

Prereqs:

- Python **3.11+**
- `uv` (https://github.com/astral-sh/uv)

Recommended environment variables (keep caches/config local):

- `UV_CACHE_DIR=.cache/uv`
- `FUNCNODES_CONFIG_DIR=.funcnodes`

Install dev dependencies:

```bash
cd funcnodes_core
UV_CACHE_DIR=.cache/uv uv sync --group dev
```

Run tests:

```bash
cd funcnodes_core
FUNCNODES_CONFIG_DIR=.funcnodes UV_CACHE_DIR=.cache/uv uv run pytest
```

## Code style & hooks

Run pre-commit:

```bash
cd funcnodes_core
UV_CACHE_DIR=.cache/uv uv run pre-commit install
UV_CACHE_DIR=.cache/uv uv run pre-commit run -a
```

## TDD expectations

- Write tests first; add edge cases as separate tests.
- Avoid mocks unless simulating external resources.

## Pull requests

- Work on a feature branch (direct commits to `main`/`master`/`test` are blocked by pre-commit).
- Keep changes scoped: core is widely used across FuncNodes packages.
