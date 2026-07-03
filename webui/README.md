# Web UI development

The backend uses FastAPI and Uvicorn. Dependencies and the virtual environment
are managed by [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn backend:app --reload --host 127.0.0.1 --port 8080
```

Then open <http://127.0.0.1:8080>. The NixOS service implementation is in
`module.nix`; settings specific to this router are in `configuration.nix`.

Run the tests with:

```bash
uv run pytest
```

API endpoints:

- `GET /api/health`
- `GET /api/status`
- `GET /api/docs`
