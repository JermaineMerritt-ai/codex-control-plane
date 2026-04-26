# codex-control-plane

FastAPI control plane for governed content and communications workflows.

## Layout

See `docs/STRUCTURE.md` for folder responsibilities.

## Dev

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```
