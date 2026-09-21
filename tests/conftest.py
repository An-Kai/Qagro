"""conftest.py — pytest-инфраструктура Qagro (только stdlib).

- Offline по умолчанию: тесты с маркером live снимаются с коллекции
  без флага --run-live (см. pytest.ini: addopts -m "not live").
- Никаких замен sys.stdout: capture pytest и так UTF-8; кириллица
  в прямых запусках чинится _fix_console() внутри __main__-блоков.
- Фикстуры изолируют записи в tmp_path: SQLite и data/gis.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_addoption(parser) -> None:
    parser.addoption("--run-live", action="store_true", default=False,
                     help="run @pytest.mark.live tests (real network, slower)")


def pytest_collection_modifyitems(config, items) -> None:
    if not config.getoption("--run-live"):
        items[:] = [i for i in items if "live" not in i.keywords]


def run_bounded(fn, timeout: float):
    """Запуск с общим timeout без новых зависимостей (Windows-safe).

    TimeoutError вместо зависания; live-тесты превращают его в skip.
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        return fut.result(timeout=timeout)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Изолированный SQLite для myfields/journal (вместо data/myfields.db)."""
    import src.journal as J
    import src.myfields as MF

    db = tmp_path / "myfields.db"
    monkeypatch.setattr(MF, "DB_PATH", db)
    monkeypatch.setattr(J, "DB_PATH", db)
    return db


@pytest.fixture
def tmp_gis(tmp_path, monkeypatch):
    """Изолированный GIS_DIR (вместо data/gis/* — tracked файлы не трогаем)."""
    import src.gis_monitor as G

    d = tmp_path / "gis"
    d.mkdir()
    monkeypatch.setattr(G, "GIS_DIR", d)
    return d


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Изолированный кэш бота (вместо data/cache.db)."""
    import src.bot as B

    db = tmp_path / "cache.db"
    monkeypatch.setattr(B, "CACHE_DB", db)
    return db
