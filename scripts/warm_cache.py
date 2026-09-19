"""warm_cache.py — прогрев офлайн-кэша для Demo Day (C8).

Что греет (всё локально, без обязательных внешних вызовов):
  1. SQLite-кэш бота data/cache.db (таблица kv, TTL 24ч, см. src/bot.py):
     - ``risk:{district}:2026`` — декадный риск Open-Meteo (снапшот);
     - ``full:{district}:{crop}:{lang}`` — готовый ответ бота
       (прогноз + страховка + совет + риск-снапшот).
  2. reports/risk_example.json — ключи ``{District}_risk`` для всех 10 районов
     (сейчас там только Esil/Zerenda; бот использует файл как fallback
     без сети через _example_risk).

Логика на район (через _risk_cached, без сети если её нет):
  HIT   — _risk_cached уже отдаёт риск (SQLite или risk_example.json):
          дублируем его в SQLite ``risk:``-ключ, чтобы боту хватило
          одного data/cache.db на демо;
  LIVE  — кэша нет, но есть интернет (--live, по умолчанию вкл):
          одна попытка decade_risk в отдельном потоке с таймаутом
          --timeout (по умолчанию 30с); успех -> SQLite + в risk_example;
  MISS  — ни кэша, ни сети: пропускаем район с пометкой MISS, exit 0
          (скрипт офлайн-безопасен, ничего не выдумываем).

``full:``-ключи считаются строго локально (compute_full: панель CSV +
пикли + yaml, 0 внешних вызовов) и потому греются даже в полном офлайне.

Запуск (из корня, интернет желателен, но не обязателен):
  python scripts/warm_cache.py
  python scripts/warm_cache.py --no-live          # только локальное (офлайн)
  python scripts/warm_cache.py --timeout 15 --year 2026
  python scripts/warm_cache.py --crops spring_wheat barley --langs ru

Проверка после:
  python -c "import sys; sys.path.insert(0,'.');
             from src.bot import _risk_cached;
             print([bool(_risk_cached(d)) for d in
                    ['Zerenda','Burabay','Atbasar','Esil','Zhaksy',
                     'Shortandy','Tselinograd','Sandyktau','Bulandy','Kokshetau']])"
  # цель демо: 10x True (все районы — HIT без сети).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from src.bot import _risk_cached, cache_set, compute_full  # noqa: E402

CONFIG = ROOT / "config" / "districts.yaml"
RISK_EXAMPLE = ROOT / "reports" / "risk_example.json"


def _districts() -> list[dict]:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("districts", [])


def _live_risk(district_en: str, year: int, timeout: float) -> dict | None:
    """Одна попытка живого риска с жёсткой границей timeout. None = нет сети."""
    from src.risk import decade_risk

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(decade_risk, district_en, year)
        try:
            res = fut.result(timeout=timeout)
        except Exception as e:  # TimeoutError / RuntimeError сети
            print(f"  [{district_en}] live FAIL ({type(e).__name__}: {str(e)[:120]})")
            return None
    if not isinstance(res, dict) or res.get("seasonal_risk") is None:
        print(f"  [{district_en}] live EMPTY (seasonal_risk=None)")
        return None
    return res


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Прогрев офлайн-кэша Qagro (C8).")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="Таймаут одного live-запроса риска, сек.")
    ap.add_argument("--live", dest="live", action="store_true", default=True,
                    help="Пробовать live decade_risk при промахе кэша (по умолч. вкл).")
    ap.add_argument("--no-live", dest="live", action="store_false",
                    help="Только локальное: без сети.")
    ap.add_argument("--crops", nargs="+", default=["spring_wheat"],
                    help="Культуры для full:-ключей (по умолч. только spring_wheat).")
    ap.add_argument("--langs", nargs="+", default=["ru"],
                    help="Языки для full:-ключей.")
    args = ap.parse_args()

    districts = _districts()
    print(f"districts: {len(districts)}, year={args.year}, "
          f"live={args.live}, timeout={args.timeout}s")
    print(f"crops={args.crops} langs={args.langs}")

    example: dict = {}
    if RISK_EXAMPLE.exists():
        try:
            example = json.loads(RISK_EXAMPLE.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            print(f"WARN: risk_example.json не читается ({e}) — начнём с {{}}.")
            example = {}
    have_keys = sorted(k for k in example if k.endswith("_risk"))
    print(f"risk_example.json: {len(have_keys)}/10 ({have_keys or 'пусто'})")

    n_hit = n_live = n_miss = 0
    n_full = 0
    new_risks = 0
    for d in districts:
        en = d["name_en"]
        # --- риск: сначала _risk_cached (SQLite -> risk_example), без сети ---
        hit = _risk_cached(en, args.year)
        status = ""
        risk_snapshot: dict | None = None
        if isinstance(hit, dict) and hit.get("seasonal_risk") is not None:
            src = hit.get("cached")
            cache_set(f"risk:{en}:{args.year}", {k: v for k, v in hit.items()
                                                 if k != "cached"})
            # дублируем примерный риск в SQLite, чтобы демо шло с одного cache.db
            n_hit += 1
            status = f"HIT (cached={src})"
            risk_snapshot = hit
        elif args.live:
            live = _live_risk(en, args.year, args.timeout)
            if live is not None:
                cache_set(f"risk:{en}:{args.year}", live)
                example[f"{en}_risk"] = live
                new_risks += 1
                n_live += 1
                status = "LIVE (saved to cache.db + risk_example)"
                risk_snapshot = live
            else:
                n_miss += 1
                status = "MISS (офлайн, без выдумок)"
        else:
            n_miss += 1
            status = "MISS (--no-live)"
        print(f"  [{en}] risk: {status}")

        # --- full-ответы: строго локально, работают и в офлайне ---
        for crop in args.crops:
            for lang in args.langs:
                try:
                    full = compute_full(en, crop, lang,
                                        risk=risk_snapshot or _risk_cached(en, args.year) or {})
                except Exception as e:
                    print(f"  [{en}/{crop}/{lang}] full FAIL: "
                          f"{type(e).__name__}: {str(e)[:150]}")
                    continue
                cache_set(f"full:{en}:{crop}:{lang}", full)
                n_full += 1
        print(f"  [{en}] full: ok ({len(args.crops) * len(args.langs)} ключей)")

    if new_risks:
        RISK_EXAMPLE.parent.mkdir(parents=True, exist_ok=True)
        RISK_EXAMPLE.write_text(json.dumps(example, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(f"WROTE {RISK_EXAMPLE} (+{new_risks} районов)")
    else:
        print(f"risk_example.json без изменений "
              f"({len([k for k in example if k.endswith('_risk')])}/10 ключей).")

    print(f"\nDONE: risk HIT={n_hit} LIVE={n_live} MISS={n_miss} "
          f"(цель демо: HIT+LIVE=10), full cached={n_full}.")
    if n_hit + n_live < len(districts):
        missing = [d["name_en"] for d in districts
                   if not _risk_cached(d["name_en"], args.year)]
        print(f"Без риска остались: {missing} — на демо для них бот покажет "
              f"светофор по p_loss с пометкой офлайн (честный fallback).")


if __name__ == "__main__":
    main()
