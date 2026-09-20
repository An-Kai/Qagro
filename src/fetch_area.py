"""fetch_area.py — посевные площади, Акмолинская область, 2005-2025.

Что делает:
  - скачивает 2 .xls БНС (stat.gov.kz, dynamic-tables akmola/1485):
      fileId=40088 — зерновые (включая рис) и бобовые, блок 1 (агрегат);
      fileId=40090 — масличные всего (блок 1) + подсолнечник (блок 2);
  - кэширует файлы в data/raw/area_40088.xls, data/raw/area_40090.xls;
  - парсит xlrd: годы из строки-заголовка (row 3), строки области + 10 районов
    из config/districts.yaml (сопоставление по русским названиям);
  - пишет data/raw/sown_area.csv: year,district_en,crop_group,area_ha,source,
    crop_group in {grain, oilseeds, sunflower}.

Единицы: 1991-1998 в файлах — тыс. га (-> x1000 в га); с 1999 — гектары.
  Нюанс (зафиксировано, вне окна 2005-2025): в блоке масличных значения
  1999-2003 области (9.0, 15.2, 8.43, 3.6, 10.07) по величине — остаточные
  тыс. га, а не га; т.к. выгружаем только 2005+, на результат не влияет.
Пропуски ('-', пусто) — пропуск строки с WARNING, без выдумок.

Проверено 2026-09-20: область oilseeds 2005=13030 / 2022=368811 /
  2023=197804 (аномалия-провал) / 2024=267675 / 2025=498610 га.

Громкий fail: недоступность без кэша, отсутствие строки области,
  rows<100, расхождение контрольных якорей -> исключение + ненулевой exit.
Зависимости: xlrd, pandas, pyyaml (уже используются в проекте).
"""

from __future__ import annotations

import logging
import sys
import urllib.request
from pathlib import Path

import pandas as pd
import xlrd
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fetch_area")

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"
RAW = ROOT / "data" / "raw"
OUT = RAW / "sown_area.csv"

TIMEOUT = 60  # секунд, по ТЗ
YEAR_MIN, YEAR_MAX = 2005, 2025

URLS: dict[int, str] = {
    40088: "https://stat.gov.kz/api/iblock/element/region/40088/file/ru/",
    40090: "https://stat.gov.kz/api/iblock/element/region/40090/file/ru/",
}
CACHE: dict[int, Path] = {
    40088: RAW / "area_40088.xls",
    40090: RAW / "area_40090.xls",
}
SOURCE_TPL = "BNS stat.gov.kz dynamic-tables akmola/1485 fileId={fid} row={label}"

OBLAST_EN = "Akmola_oblast"  # итог области отдельной строкой district_en
OBLAST_LABELS = {"по области", "всего по области"}

# Контрольные якоря области (га), сверены с AREA_FEASIBILITY.md / прямым парсингом.
CHECKS: list[tuple[str, int, int]] = [
    ("oilseeds", 2005, 13030),
    ("oilseeds", 2023, 197804),  # аномалия-провал между 2022=368811 и 2024=267675
    ("oilseeds", 2024, 267675),
    ("grain", 2005, 3604292),
    ("grain", 2024, 4693012),
    ("sunflower", 2005, 10002),
    ("sunflower", 2024, 91588),
]


def norm_label(s: object) -> str:
    t = str(s).replace("\n", " ").strip().lower()
    t = t.replace("г.а.", "").replace("г.а", "").replace(".", "")
    return " ".join(t.split())


def load_district_map() -> dict[str, str]:
    """ru-нормализованное имя из файла -> name_en из config."""
    if not CONFIG.exists():
        raise FileNotFoundError(f"config not found: {CONFIG}")
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    mapping: dict[str, str] = {}
    for d in cfg.get("districts", []):
        mapping[norm_label(d["name_ru"])] = d["name_en"]
    if len(mapping) < 10:
        raise ValueError(f"districts.yaml: expected >=10 districts, got {len(mapping)}")
    return mapping


def download(fid: int) -> bytes:
    url = URLS[fid]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Qagro-dataeng"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read()
    except Exception as e:
        if CACHE[fid].exists():
            log.warning("Download fileId=%d failed (%r) — использую кэш %s", fid, e, CACHE[fid])
            return CACHE[fid].read_bytes()
        log.error(
            "STOP: fileId=%d недоступен (timeout=%dс, ошибка %r), кэша %s нет. "
            "Отчет: stat.gov.kz dynamic-tables akmola/1485, URL %s. "
            "CSV не собран, панель/модели не тронуты.",
            fid, TIMEOUT, e, CACHE[fid], url,
        )
        raise SystemExit(f"fetch_area STOP: fileId={fid} download failed, no cache: {e!r}")
    if not data[:8].startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError(f"fileId={fid}: не OLE .xls (первые байты {data[:8]!r})")
    RAW.mkdir(parents=True, exist_ok=True)
    CACHE[fid].write_bytes(data)
    log.info("Скачан fileId=%d: %d байт -> %s", fid, len(data), CACHE[fid])
    return data


def to_ha(raw: object, year: int) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
        if s in ("", "-", "–", "—", "н/д", "x", "...", "…"):
            return None
        try:
            v = float(s)
        except ValueError:
            return None
    else:
        try:
            v = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
    if year <= 1998:
        v *= 1000.0  # тыс. га -> га
    if v <= 0:
        # Явный 0 (напр. г. Кокшетау, масличные-2016: 0.0 между 912 и 995 га) —
        # посева не было/не учтен: пропуск с логом, как '-' (без выдумок).
        return None
    return int(round(v))


def parse_block(data: bytes, fid: int, crop_group: str, block_no: int,
                dmap: dict[str, str]) -> list[dict]:
    """Парсит один блок листа: строка области + районные строки."""
    wb = xlrd.open_workbook(file_contents=data)
    sh = wb.sheet_by_index(0)
    years = [int(float(sh.cell_value(3, j))) for j in range(1, sh.ncols)]
    # Индексы строк "Всего/по области": block_no=1 -> первое вхождение, 2 -> второе.
    oblast_idxs = [
        i for i in range(sh.nrows)
        if norm_label(sh.cell_value(i, 0)) in OBLAST_LABELS
    ]
    if len(oblast_idxs) < block_no:
        raise ValueError(
            f"fileId={fid} {crop_group}: строка области (блок {block_no}) не найдена "
            f"(найдено {len(oblast_idxs)}: {oblast_idxs})"
        )
    oi = oblast_idxs[block_no - 1]
    oblast_label = str(sh.cell_value(oi, 0)).strip()
    # Районные строки: после области до пустой/заголовочной строки или конца блока.
    end = oblast_idxs[block_no] if len(oblast_idxs) > block_no else sh.nrows
    rows: list[dict] = []
    skipped = 0
    targets: list[tuple[int, str, str]] = [(oi, OBLAST_EN, oblast_label)]
    for i in range(oi + 1, end):
        lab = str(sh.cell_value(i, 0)).strip()
        if not lab:
            break
        key = norm_label(lab)
        en = dmap.get(key)
        if en is None:
            continue  # чужой район/г.а. (Аккольский, Косшы и т.д.) — не наши 10
        targets.append((i, en, lab))
    found_en = {en for _, en, _ in targets} - {OBLAST_EN}
    missing = set(dmap.values()) - found_en
    if missing:
        log.warning("fileId=%d %s: нет строк районов %s — пропуск без выдумок",
                    fid, crop_group, sorted(missing))
    for i, en, lab in targets:
        for j, y in enumerate(years, start=1):
            if not (YEAR_MIN <= y <= YEAR_MAX):
                continue
            v = to_ha(sh.cell_value(i, j), y)
            if v is None:
                skipped += 1
                continue
            rows.append({
                "year": y,
                "district_en": en,
                "crop_group": crop_group,
                "area_ha": v,
                "source": SOURCE_TPL.format(fid=fid, label=lab),
            })
    log.info("fileId=%d %s: строк=%d (область row=%d + районов=%d), пропусков '-'/пусто=%d",
             fid, crop_group, len(rows), oi, len(targets) - 1, skipped)
    return rows


def validate(df: pd.DataFrame) -> None:
    assert list(df.columns) == ["year", "district_en", "crop_group", "area_ha", "source"], \
        f"Bad columns: {list(df.columns)}"
    if df.empty:
        raise ValueError("sown_area пуст — FAIL")
    if len(df) < 100:
        raise ValueError(f"sown_area rows={len(df)} < 100 — FAIL")
    if df["area_ha"].isna().any() or (df["area_ha"] <= 0).any():
        raise ValueError("NaN/неположительные area_ha — FAIL")
    ob = df[df["district_en"] == OBLAST_EN]
    for crop, year, expect in CHECKS:
        got = ob[(ob["crop_group"] == crop) & (ob["year"] == year)]["area_ha"]
        if got.empty:
            raise ValueError(f"Нет строки области {crop} {year} — FAIL")
        if abs(int(got.iloc[0]) - expect) > max(1500, expect * 0.01):
            raise ValueError(f"Якорь {crop} {year}: {int(got.iloc[0])} vs ожид. ~{expect} — FAIL")
    o05 = int(ob[(ob["crop_group"] == "oilseeds") & (ob["year"] == 2005)]["area_ha"].iloc[0])
    o24 = int(ob[(ob["crop_group"] == "oilseeds") & (ob["year"] == 2024)]["area_ha"].iloc[0])
    o22 = int(ob[(ob["crop_group"] == "oilseeds") & (ob["year"] == 2022)]["area_ha"].iloc[0])
    o23 = int(ob[(ob["crop_group"] == "oilseeds") & (ob["year"] == 2023)]["area_ha"].iloc[0])
    log.info("Контроль сдвига: oilseeds области 2005=%d -> 2024=%d (x%.1f)", o05, o24, o24 / o05)
    log.info("Аномалия 2023 ПОДТВЕРЖДЕНА парсингом: %d (2022) -> %d (2023) -> %d (2024)",
             o22, o23, o24)


def main() -> None:
    try:
        dmap = load_district_map()
        d88 = download(40088)
        d90 = download(40090)
        rows: list[dict] = []
        rows += parse_block(d88, 40088, "grain", 1, dmap)       # зерновые, блок 1
        rows += parse_block(d90, 40090, "oilseeds", 1, dmap)    # масличные всего
        rows += parse_block(d90, 40090, "sunflower", 2, dmap)   # подсолнечник
        df = pd.DataFrame(rows, columns=["year", "district_en", "crop_group", "area_ha", "source"])
        df = df.sort_values(["crop_group", "district_en", "year"]).reset_index(drop=True)
        validate(df)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT, index=False)
        log.info("WROTE %s rows=%d years=%d-%d districts=%d groups=%s",
                 OUT, len(df), df["year"].min(), df["year"].max(),
                 df["district_en"].nunique(), sorted(df["crop_group"].unique()))
    except SystemExit:
        raise
    except Exception as e:
        log.exception("FATAL fetch_area failed (no mocks, loud fail): %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
