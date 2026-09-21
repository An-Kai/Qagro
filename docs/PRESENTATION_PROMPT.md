# Qagro - промпт пересборки колоды (10 слайдов)

Скопируй блок ниже целиком и вставь исполнителю. Промпт тянет числа только из правды репо и пересобирает PDF.

```text
Ты инженер презентации в репо Qagro (Windows). Без сети. Код модели и данных не менять. Итог: PDF docs/Qagro_presentation.pdf, ровно 10 слайдов.

1) Числа брать ТОЛЬКО из четырех файлов. Прочитай их командами:
Get-Content metrics/metrics.json -Encoding UTF8
Get-Content metrics/intervals.json -Encoding UTF8
python -c "import json;d=json.load(open('reports/risk_example.json',encoding='utf-8'));print(d['Esil_insurance_wheat']);print(d['Zerenda_insurance_wheat']);print(d['Esil_risk']['seasonal_risk'],d['Esil_risk']['seasonal_light']);print(d['Zerenda_risk']['seasonal_risk'],d['Zerenda_risk']['seasonal_light'])"
python -c "import json;d=json.load(open('data/ndvi/ndvi_timeseries.json',encoding='utf-8'));print('real=',len([x for x in d if x.get('ndvi_mean') is not None]),'total=',len(d))"
Зафиксируй: пшеница/ячмень/овес MAE и R2 (поле lgbm) плюс бейзлайн; покрытие wheat из intervals.json; Esil и Zerenda: y_pred_c_ha, p_loss, expected_payout_ha, seasonal_risk и светофор; число real NDVI. Сверочные якоря на 20.09.2026: Esil y_pred 11.39, payout 51, p_loss 0.0176, риск 35.0 желтый; Zerenda y_pred 12.66, payout 52, p_loss 0.018, риск 28.5 зеленый. Если в файлах другое - верны файлы, якоря устарели.
2) Жесткие рамки: PDF; РОВНО 10 слайдов; A4 landscape; шрифт с кириллицей DejaVu/Arial (если его нет - честное предупреждение на титуле); футер N/10 и слово Qagro на каждом слайде; скелет: 1 проблема / 2 решение / 3 демо / 4 данные / 5 модель / 6 метрики / 7 эффект / 8 масштаб / 9 команда / 10 планы. Слайд 6: чарт metrics/plots/scatter_spring_wheat.png. Слайд 7: таблица выплат из risk_example.json (Есильский 51 тг/га, Зерендинский 52 тг/га).
3) Стиль для жюри и фермера: один буллет - одно число; термин только с переводом на простой русский (MAE - средняя ошибка в ц/га; R2 - насколько модель лучше среднего); честные пределы на слайдах 5-6: лен experimental (ниже бейзлайна), рапс с оговоркой по R2, покрытие wheat 0.66, номинал 0.80 не заявлять; район - даунскейлинг области на центроиды; страховка - decision support, не тариф. Без суперлативов и жаргона без перевода.
4) Сборка и проверка:
python scripts/build_presentation.py
python -c "from pypdf import PdfReader;r=PdfReader('docs/Qagro_presentation.pdf');assert len(r.pages)==10,len(r.pages);print('pages=10 OK');[print(i+1,('%d/10'%(i+1)) in (r.pages[i].extract_text() or '')) for i in range(10)]"
Все 10 проверок футера - True. Если нет - чинить сборку, числа не выдумывать.
```

## Когда перезапускать (заметка мейнтейнера)

1. Сменились metrics.json или intervals.json (переобучение, новый hold-out) - слайды 5-6.
2. Сменился risk_example.json (regen_risk_example.py) - слайды 3 и 7.
3. Сменился ndvi_timeseries.json (новые real сцены) - слайд 4.
4. Сменилась панель (строки/колонки) или число полей - слайд 4.
5. Сменились цены/субсидия в страховке - слайд 7.
6. Сменились состав команды, хаб, даты хакатона - слайд 9.
7. Сменился план работ (почва, NDVI-ряд, е-АПК) - слайд 10.
8. Жюри просит другой скелет - править скелет здесь и в build_presentation.py вместе.
9. Поплыл шрифт/футеры/число страниц - чинить сборку, потом гнать проверку из блока.
10. После каждого прогона сверить PDF с outline и demo_script, разницу зафиксировать.
