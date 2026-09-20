"""test_bot_texts.py — тексты и клавиатуры бота без Telegram-сети.

Запуск: python tests/test_bot_texts.py
Проверки:
- T/HELP_TEXT/MORE_TEXT: паритет ключей ru/kz/en, без tech-маркировки.
- MORE_TEXT упоминает только существующие команды (есть хендлеры).
- HELP короткий (3 сценария), полный список — в /more.
- spray._fmt_window: окно в 1 час не показывает "с X до X".
- create_dispatcher собирается (aiogram установлен).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bot import HELP_TEXT, MORE_TEXT, T, create_dispatcher  # noqa: E402
from src.spray import _fmt_window  # noqa: E402

LANGS = ("ru", "kz", "en")
passed: list[str] = []


def check(name: str, fn) -> None:
    fn()
    passed.append(name)
    print(f"PASS: {name}")


def t_t_parity():
    for key, val in T.items():
        assert set(val.keys()) == set(LANGS), f"T[{key}]: {sorted(val.keys())}"


def t_help_more_parity():
    assert set(HELP_TEXT.keys()) == set(LANGS), sorted(HELP_TEXT.keys())
    assert set(MORE_TEXT.keys()) == set(LANGS), sorted(MORE_TEXT.keys())
    # HELP — короткий (есть ссылка на /more), полный список — в MORE
    for lang in LANGS:
        assert "/more" in HELP_TEXT[lang], lang
        assert "/gis" not in HELP_TEXT[lang], f" HELP[{lang}] still lists /gis"
        assert "/gis" in MORE_TEXT[lang] and "/spray" in MORE_TEXT[lang], lang


def t_more_cmds_exist():
    src = (ROOT / "src" / "bot.py").read_text(encoding="utf-8")
    for lang in LANGS:
        for cmd in re.findall(r"• /([a-z_]+)", MORE_TEXT[lang]):
            assert f'Command("{cmd}")' in src, f"/{cmd} без хендлера"


def t_no_tech_in_buttons():
    for lang in LANGS:
        assert "Share Location" not in T["btn_location"][lang] or lang == "en"
        assert T["btn_spray"][lang] != "🧴 Spray" or lang == "en"


def t_fmt_window_single_hour():
    ru = _fmt_window("2026-09-20T23:00", "2026-09-20T23:00", "ru")
    assert "до 23:00" not in ru, ru
    assert "23:00" in ru, ru
    en = _fmt_window("2026-09-20T23:00", "2026-09-20T23:00", "en")
    assert "at 23:00" in en, en
    rng = _fmt_window("2026-09-20T20:00", "2026-09-21T02:00", "ru")
    assert "20.09" in rng and "21.09" in rng, rng


def t_dispatcher_builds():
    dp = create_dispatcher()
    n = len(dp.message.handlers) + len(dp.callback_query.handlers)
    assert n >= 20, f"мало хендлеров: {n}"


if __name__ == "__main__":
    check("T ru/kz/en parity", t_t_parity)
    check("HELP short + MORE full", t_help_more_parity)
    check("MORE cmds have handlers", t_more_cmds_exist)
    check("buttons localized", t_no_tech_in_buttons)
    check("spray single-hour window", t_fmt_window_single_hour)
    check("dispatcher builds", t_dispatcher_builds)
    print(f"OK: {len(passed)}/{len(passed)} — {', '.join(passed)}")
