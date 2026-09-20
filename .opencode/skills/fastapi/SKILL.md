---
name: fastapi
description: FastAPI best practices and conventions. Use when working with FastAPI APIs, Pydantic models, dependencies, streaming responses including Server-Sent Events (SSE), and serving frontend apps. Keeps FastAPI code clean and up to date with the latest features and patterns.
license: MIT
compatibility: opencode
---

# FastAPI

Official FastAPI skill to write code with best practices, keeping up to date with new versions and features.

Source: https://github.com/fastapi/fastapi (path `fastapi/.agents/skills/fastapi/SKILL.md`).
Reference files (`references/*.md`: streaming, dependencies, responses, pydantic,
path-operations, other-tools) live upstream; consult them in the fastapi repo when needed.

## Quick Reference

* Dependencies: use `Annotated[..., Depends(...)]`; see Dependency Injection below
  for `yield`, scopes, and class dependencies.
* Response models: prefer return types; use `response_model` when the public response
  schema differs from the internal return value.
* Pydantic models: do not use ellipsis (`...`) or `RootModel`.
* Routing: declare router-level prefix, tags, and shared dependencies on the `APIRouter`.
* Tooling: use uv, Ruff, ty, Asyncer, SQLModel, and HTTPX when applicable.

## Use the `fastapi` CLI

Run the development server on localhost with reload:

```bash
fastapi dev
```

Run the production server:

```bash
fastapi run
```

Prefer declaring the entrypoint in `pyproject.toml`:

```toml
[tool.fastapi]
entrypoint = "my_app.main:app"
```

## Use `Annotated`

Always prefer the `Annotated` style for parameter and dependency declarations.

```python
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Query

app = FastAPI()


def get_current_user():
    return {"username": "johndoe"}


CurrentUserDep = Annotated[dict, Depends(get_current_user)]


@app.get("/items/{item_id}")
async def read_item(
    item_id: Annotated[int, Path(ge=1, description="The item ID")],
    q: Annotated[str | None, Query(max_length=50)] = None,
    current_user: CurrentUserDep | None = None,
):
    return {"message": "Hello World"}
```

## Do not use Ellipsis for path operations or Pydantic models

Do not use `...` as a default value for required parameters or model fields.

```python
from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float = Field(gt=0)


@app.post("/items/")
async def create_item(item: Item, project_id: Annotated[int, Query()]):
    return item
```

## Return Type or Response Model

When possible, include a return type. It will be used to validate, filter, document,
and serialize the response. Return types filter data to avoid exposing sensitive
information, and let Pydantic serialize on the Rust side for performance.

Use `response_model` when the type you return is not the same as the public schema
you want to validate, filter, document, and serialize.

## Performance

Do not use `ORJSONResponse` or `UJSONResponse`, they are deprecated.
Instead, declare a return type or response model.

## Including Routers

Prefer router-level parameters like prefix, tags, and shared dependencies on the
router itself instead of in `include_router()`.

```python
from fastapi import APIRouter, Depends, FastAPI

app = FastAPI()


def get_current_user():
    return {"username": "johndoe"}


router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/")
async def list_items():
    return []


app.include_router(router)
```

## Dependency Injection

Use dependencies when the logic can't be declared in Pydantic validation, depends on
external resources, needs cleanup with `yield`, or is shared across endpoints.
Apply shared dependencies at the router level via `dependencies=[Depends(...)]`.

## Async vs Sync path operations

Use `async` path operations only when fully certain that the logic called inside is
compatible with async and await, and that it doesn't block. In case of doubt, or by
default, use regular `def` functions — they run in a threadpool and don't block the
event loop. The same rules apply to dependencies.

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/async-items/")
async def read_async_items():
    data = await some_async_library.fetch_items()
    return data


@app.get("/items/")
def read_items():
    data = some_blocking_library.fetch_items()
    return data
```

## Use one HTTP operation per function

Don't mix HTTP operations in a single function.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str


@app.get("/items/")
async def list_items():
    return []


@app.post("/items/")
async def create_item(item: Item):
    return item
```

## Do not use Pydantic RootModels

Do not use Pydantic `RootModel`; instead use regular type annotations with
`Annotated` and Pydantic validation utilities. FastAPI creates a Pydantic
`TypeAdapter` for them.

---

## Qagro appendix (project-specific, takes precedence in this repo)

Qagro API: `src/api.py` (`FastAPI(title="Qagro API")`), extended by
`src/platform_api.py` router (`myfields/journal/spray/guide/NPK/economy`).

Conventions (do not "fix" these to generic patterns):

- Launch: `python -m uvicorn src.api:app --host 127.0.0.1 --port 8000`
  (NOT `fastapi dev` — repo pins `fastapi==0.116.1`, `uvicorn==0.35.0`,
  entrypoint `src.api:app`; Windows: run via `python -m ...` or `run_api.bat`).
- Blocking ML/pandas work inside endpoints stays in plain `def` handlers
  (threadpool) — matches "Async vs Sync" rule above; `predict` is CPU-bound.
- In-memory predict cache 5 min (`_PREDICT_CACHE`, TTL 300, header
  `X-Qagro-Cache: HIT/MISS`); `?fresh=true` bypasses it. Keep it.
- `ValueError` -> 422 with RU/EN message (`_value_error_handler`, `_err422`);
  missing data files -> 500/404 with honest "run script X first" text, never mocks.
- Open-Meteo-dependent parts (`_safe_risk`, `/alerts`, spray) are best-effort:
  on network error return `{"error": ..., "seasonal_risk": None}` / empty alerts
  with HTTP 200 — never invent numbers.
- CORS `allow_origins=["*"]` is intentional (bot/Streamlit call from other origins).
- `GET /version` (git sha + build date), `GET /metrics`, `/districts`, `/fields`,
  `/granaries`, `/soil`, `/intervals`, `/gis`, `/compare`, `/season`, `/guide`,
  `/fertilizer`, `/economy` are read-only projections over repo files — keep them
  offline-safe with explicit errors.
- Pydantic models: `PredictRequest` / `ReportRequest` (`district_en`, `crop`,
  `lang ru|kz|en`, `weather dict|None`, `year`, `include_risk`). Validate against
  `config/districts.yaml` + `ALL_CROPS` (`src/approx_crops.py`); unknown values
  raise `ValueError` (422), never default silently.
- `POST /report` returns raw PDF bytes (`Response`, `media_type="application/pdf"`)
  built by `src/report_pdf.py` (see `pdf` skill for Cyrillic/DejaVu rules).
- Keep `model-serving` skill patterns for artifact loading
  (`models/lgbm_*.pkl` loaded once via `src/predict.py`) and `agro-analytics`
  no-mock policy for all `/predict` changes.
