# Поля Акмолы — методика (v2)

## Что это
`akmola_osm_fields.geojson` — оцифрованные контуры сельхозполей вокруг
10 райцентров из `config/districts.yaml`. Формат: Polygon/MultiPolygon (WGS84).
Свойства каждого полигона: `district_en`, `area_ha`, `source`, плюс
`demo` (false = реальный OSM, true = демо-заглушка), для OSM — `osm_type`/`osm_id`.

## Методика
1. Для каждого райцентра — запрос к Overpass API
   `https://overpass-api.de/api/interpreter` (Overpass QL):
   ```
   [out:json][timeout:60];
   (nwr["landuse"="farmland"](around:15000,lat,lon););
   out geom 15;
   ```
   Радиус 15000 м, лимит 15 полигонов на район, timeout 60 с.
   Скрипт: `python src/fields_osm.py` (см. `src/fields_osm.py`).
2. Ways с `geometry` → Polygon; relations (outer-члены) → Polygon/MultiPolygon.
   Точечные nodes отбрасываются (нужны только поля-полигоны).
3. Площадь `area_ha`: haversine approx — equirectangular проекция
   (x = lon·R·cos(lat0), y = lat·R) + формула шнурка, /10000. Точности
   достаточно для полей масштаба ~км на 51–53°N; без geopandas/shapely,
   чистый Python.
4. Если Overpass вернул 0 полигонов или ошибку сети/таймаут для района —
   генерируются **3 честных демо-прямоугольника 1×2 км (~200 га)** вокруг
   центра со смещениями (−4,−3), (2,2), (5,−2) км, с флагом `demo:true`
   и `source:"demo-fallback"`. Это НЕ данные OSM и так подписано.

## Источники (все указаны, без моков)
- **OpenStreetMap** через Overpass API, лицензия данных **ODbL**
  https://www.openstreetmap.org/copyright
- **Geofabrik Kazakhstan** (запасной офлайн-дамп, ODbL):
  https://download.geofabrik.de/asia/kazakhstan.html
  — скачать `kazakhstan-latest.osm.pbf`, отфильтровать `landuse=farmland`
  (напр. `osmium tags-filter ... landuse=farmland`), сконвертировать в GeoJSON.
- **map.iaqmola.kz (Smart GeoHub)** — официальный источник границ полей
  для пилота в Акмолинской области. Требует авторизации, публичного
  WFS/API без ключа нет, поэтому **OSM — открытая замена на хакатон**,
  а для продакшена — импорт ниже.
- **Элеваторы**: `data/fields/granaries.json`, перечень по карте Qoldau
  https://p-grain-receipt.qoldau.kz/ru/gr-info/granaries-map
  (карта на JS без публичного API; координаты оценочные по OSM,
  подлежат уточнению).

## Инструкция импорта официальных полей (map.iaqmola.kz → GeoJSON)
1. Получить доступ к Smart GeoHub (map.iaqmola.kz) у акимата/оператора пилота.
2. Выгрузить слой полей/пашен Акмолинской области (обычно Shp/GeoJSON/WFS).
3. Привести к WGS84 (EPSG:4326), оставить Polygon/MultiPolygon.
4. Добавить свойства `district_en` (джойн по райцентру/акимату),
   посчитать `area_ha`, поставить `source:"iaqmola Smart GeoHub"`, `demo:false`.
5. Положить как `data/fields/akmola_official_fields.geojson` и переключить
   `src/api.py /fields` и `app/streamlit_app.py` на официальный файл
   (OSM-файл оставить как fallback с указанием источника).

## Воспроизводимость
```powershell
pip install requests pyyaml
python src/fields_osm.py
```
Проверка: файл создан, валидный GeoJSON, сводка «реальных OSM vs demo»
печатается в консоль и дублируется в `metadata` внутри GeoJSON.
