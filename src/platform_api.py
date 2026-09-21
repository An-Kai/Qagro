"""platform_api.py — роутер платформы фермера (Qagro v4).

FastAPI APIRouter, подключён в src/api.py через app.include_router:
    GET    /myfields              -> список полей
    POST   /myfields              -> создать поле
    DELETE /myfields/{field_id}   -> удалить поле
    GET    /journal?field_id=..   -> заметки поля
    POST   /journal               -> добавить заметку
    GET    /spray?district_en=..  -> окно опрыскивания (живой Open-Meteo)

Чистые функции лежат в src/myfields.py, src/journal.py, src/spray.py —
здесь только тонкие HTTP-обёртки.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

try:  # пакетный запуск (uvicorn/pytest из корня, src — пакет)
    from src.journal import PROBLEM_TYPES, add_note, list_notes
    from src.myfields import add_field, delete_field, list_fields
    from src.spray import check_spray_window
except ImportError:  # прямое использование из папки src/
    from journal import PROBLEM_TYPES, add_note, list_notes  # type: ignore
    from myfields import add_field, delete_field, list_fields  # type: ignore
    from spray import check_spray_window  # type: ignore

router = APIRouter(tags=["platform"])


# ---------------------------------------------------------------- models
class FieldCreate(BaseModel):
    name: str = Field(examples=["Поле у речки"])
    lat: float = Field(examples=[51.95])
    lon: float = Field(examples=[66.40])
    area_ha: float = Field(examples=[120.0])
    crop: str = Field(examples=["spring_wheat"])


class NoteCreate(BaseModel):
    field_id: int = Field(examples=[1])
    problem_type: str = Field(examples=["weeds"])
    text: str = Field(examples=["Осот по краю поля"])
    date: str | None = Field(default=None, examples=["2026-09-19"])


# ---------------------------------------------------------------- routes
@router.get("/myfields")
def api_list_fields() -> dict:
    fields = list_fields()
    return {"fields": fields, "count": len(fields)}


@router.post("/myfields", status_code=201)
def api_add_field(body: FieldCreate) -> dict:
    try:
        return add_field(body.name, body.lat, body.lon, body.area_ha, body.crop)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/myfields/{field_id}")
def api_delete_field(field_id: int) -> dict:
    try:
        ok = delete_field(field_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail=f"field_id={field_id} не найден.")
    return {"ok": True, "id": field_id}


@router.get("/journal")
def api_list_notes(
    field_id: int = Query(description="ID поля из /myfields"),
) -> dict:
    try:
        notes = list_notes(field_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"field_id": field_id, "notes": notes, "count": len(notes)}


@router.post("/journal", status_code=201)
def api_add_note(body: NoteCreate) -> dict:
    if body.problem_type not in PROBLEM_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(f"problem_type={body.problem_type!r} неизвестен. "
                    f"Допустимо: {sorted(PROBLEM_TYPES)}."),
        )
    try:
        return add_note(body.field_id, body.problem_type, body.text, body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/spray")
def api_spray(
    district_en: str = Query(examples=["Esil"]),
    hours: int = Query(default=48, ge=1, le=384),
) -> dict:
    """Окно опрыскивания. Офлайн Open-Meteo -> 502 с честной ошибкой."""
    try:
        return check_spray_window(district_en, hours)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
