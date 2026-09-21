"""guide_data.py — справочник болезней и вредителей (Qagro v4).

Источник: опыт региона + university guidelines.
Подпись источника каждого факта: source="agro-practice".
Дозировки НЕ указываются intentionally — только класс обработки по регламенту,
точную схему назначает агроном по факту осмотра.
Без брендов препаратов.
"""

from __future__ import annotations

SOURCE = "agro-practice"

GUIDE: dict[str, list[dict]] = {
    "wheat": [
        {
            "id": "wheat_leaf_rust",
            "crops": ["wheat"],
            "names": {
                "ru": "Листовая (бурая) ржавчина пшеницы",
                "kz": "Бидайдың жапырақ (қоңыр) таты",
                "en": "Wheat leaf (brown) rust",
            },
            "signs": {
                "ru": [
                    "Оранжево-бурые порошащие пустулы на верхней стороне листьев",
                    "Пустулы расположены беспорядочно, лист желтеет вокруг них",
                    "При сильном развитии листья усыхают, зерно щуплое",
                ],
                "kz": [
                    "Жапырақтың үстіңгі жағында сарғыш-қоңыр ұнтақты пустулалар",
                    "Пустулалар ретсіз орналасады, айналасы сарғаяды",
                    "Қатты зақымданса жапырақ қурап, дән толықсымайды",
                ],
                "en": [
                    "Orange-brown powdery pustules on upper leaf surface",
                    "Pustules scattered randomly, yellowing around them",
                    "Severe attack dries leaves and shrivels grain",
                ],
            },
            "action": {
                "ru": "Триазольный фунгицид по регламенту при первых пустулах; севооборот, устойчивые сорта",
                "kz": "Алғашқы пустулаларда регламент бойынша триазол класындағы фунгицид; ауыспалы егіс, төзімді сорттар",
                "en": "Triazole-class fungicide per label at first pustules; rotation, resistant varieties",
            },
            "danger": 2,
            "source": SOURCE,
        },
        {
            "id": "wheat_septoria",
            "crops": ["wheat"],
            "names": {
                "ru": "Септориоз пшеницы",
                "kz": "Бидай септориозы",
                "en": "Wheat septoria tritici blotch",
            },
            "signs": {
                "ru": [
                    "Светлые овальные пятна с тёмной каймой на нижних листьях",
                    "Внутри пятен мелкие чёрные точки (пикниды)",
                    "Пятна сливаются снизу вверх, листья отмирают",
                ],
                "kz": [
                    "Төменгі жапырақтарда қара жиекті ашық сопақ дақтар",
                    "Дақ ішінде ұсақ қара нүктелер (пикнидалар)",
                    "Дақтар төменнен жоғары қосылып, жапырақ қурайды",
                ],
                "en": [
                    "Pale oval lesions with dark borders on lower leaves",
                    "Tiny black dots (pycnidia) inside lesions",
                    "Lesions merge bottom-up, leaves die off",
                ],
            },
            "action": {
                "ru": "Триазол-содержащий фунгицид по регламенту; заделка стерни, севооборот",
                "kz": "Регламент бойынша триазолды фунгицид; сабан қалдығын сіңіру, ауыспалы егіс",
                "en": "Triazole-containing fungicide per label; stubble incorporation, rotation",
            },
            "danger": 2,
            "source": SOURCE,
        },
        {
            "id": "wheat_loose_smut",
            "crops": ["wheat"],
            "names": {
                "ru": "Пыльная головня пшеницы",
                "kz": "Бидайдың шаңды қара күйесі",
                "en": "Wheat loose smut",
            },
            "signs": {
                "ru": [
                    "Вместо колоса — чёрная пылящая масса спор в фазу колошения",
                    "Стебель поражённого растения часто выше здоровых",
                    "К уборке от колоса остаётся голый стержень",
                ],
                "kz": [
                    "Масақтануда масақ орнына қара шаңды спора массасы",
                    "Зақымдалған сабақ көбіне сауларынан биік болады",
                    "Оруға қарай масақтан жалаңаш өзек қалады",
                ],
                "en": [
                    "Black dusty spore mass instead of ear at heading",
                    "Infected stems often taller than healthy ones",
                    "Only bare rachis remains by harvest",
                ],
            },
            "action": {
                "ru": "Системное протравливание семян (триазольный класс) по регламенту; выбраковка семенных участков с головнёй",
                "kz": "Регламент бойынша тұқымды жүйелі триазол класымен дәрілеу; қара күйелі тұқым учаскелерін егуге пайдаланбау",
                "en": "Systemic seed treatment (triazole class) per label; reject seed lots from smutted fields",
            },
            "danger": 3,
            "source": SOURCE,
        },
    ],
    "barley": [
        {
            "id": "barley_stripe",
            "crops": ["barley"],
            "names": {
                "ru": "Полосатая пятнистость (гельминтоспориоз) ячменя",
                "kz": "Арпаның жолақты дағы (гельминтоспориоз)",
                "en": "Barley stripe disease",
            },
            "signs": {
                "ru": [
                    "Жёлто-коричневые продольные полосы вдоль листа",
                    "Полосы темнеют, лист расщепляется вдоль",
                    "Растения отстают в росте, колос щуплый",
                ],
                "kz": [
                    "Жапырақ бойымен сары-қоңыр ұзын жолақтар",
                    "Жолақтар қарайып, жапырақ бойлай жыртылады",
                    "Өсімдік өсуден қалып, масақ толықсымайды",
                ],
                "en": [
                    "Yellow-brown longitudinal stripes along the leaf",
                    "Stripes darken, leaf splits lengthwise",
                    "Stunted plants, shrivelled ears",
                ],
            },
            "action": {
                "ru": "Протравливание семян системным фунгицидом по регламенту; севооборот, заделка растительных остатков",
                "kz": "Тұқымды регламент бойынша жүйелі фунгицидпен дәрілеу; ауыспалы егіс, өсімдік қалдығын сіңіру",
                "en": "Systemic seed treatment per label; rotation, residue incorporation",
            },
            "danger": 2,
            "source": SOURCE,
        },
        {
            "id": "barley_rust",
            "crops": ["barley"],
            "names": {
                "ru": "Ржавчина ячменя",
                "kz": "Арпа таты",
                "en": "Barley rust",
            },
            "signs": {
                "ru": [
                    "Мелкие оранжево-коричневые пустулы на листьях и стеблях",
                    "Вокруг пустул светло-жёлтый ореол",
                    "При эпифитотии листья усыхают досрочно",
                ],
                "kz": [
                    "Жапырақ пен сабақта ұсақ сарғыш-қоңыр пустулалар",
                    "Пустула айналасында ашық сары жиек",
                    "Эпифитотияда жапырақ ерте қурайды",
                ],
                "en": [
                    "Small orange-brown pustules on leaves and stems",
                    "Pale-yellow halo around pustules",
                    "Leaves dry prematurely in epidemics",
                ],
            },
            "action": {
                "ru": "Триазольный фунгицид по регламенту при нарастании пустул; устойчивые сорта",
                "kz": "Пустула көбейсе регламент бойынша триазолды фунгицид; төзімді сорттар",
                "en": "Triazole-class fungicide per label as pustules spread; resistant varieties",
            },
            "danger": 2,
            "source": SOURCE,
        },
    ],
    "sunflower": [
        {
            "id": "sunflower_white_rot",
            "crops": ["sunflower"],
            "names": {
                "ru": "Белая гниль (склеротиниоз) подсолнечника",
                "kz": "Күнбағыстың ақ шірігі (склеротиниоз)",
                "en": "Sunflower white rot (Sclerotinia)",
            },
            "signs": {
                "ru": [
                    "Белый ватообразный налёт на стебле, корзинке или корнях",
                    "Ткани буреют и размягчаются, стебель надламывается",
                    "Внутри стебля/корзинки чёрные склероции",
                ],
                "kz": [
                    "Сабақ, себет немесе тамырда ақ мақта тәрізді өңез",
                    "Тіндер қоңырланып жұмсарады, сабақ сынады",
                    "Сабақ/себет ішінде қара склероцийлер",
                ],
                "en": [
                    "White cottony mycelium on stem, head or roots",
                    "Tissues brown and soften, stem snaps",
                    "Black sclerotia inside stem/head",
                ],
            },
            "action": {
                "ru": "Севооборот с возвратом подсолнечника не раньше 5–7 лет; агротехника и уборка без потерь; фунгицидная защита по регламенту",
                "kz": "Күнбағысты 5–7 жылдан ерте қайтармау; агротехника, шығынсыз жинау; регламент бойынша фунгицидтік қорғау",
                "en": "Rotate sunflower no sooner than every 5-7 years; sound agronomy, lossless harvest; fungicide protection per label",
            },
            "danger": 3,
            "source": SOURCE,
        },
    ],
    "common": [
        {
            "id": "pest_locust",
            "crops": ["wheat", "barley", "oats", "sunflower", "rapeseed", "flax"],
            "names": {
                "ru": "Саранча",
                "kz": "Шегіртке",
                "en": "Locusts",
            },
            "signs": {
                "ru": [
                    "Стаи/скопления прыгающих и летающих насекомых",
                    "Объеденные листья, стебли, колосья и корзинки",
                    "Очаги вблизи залежей и пастбищ в жаркую сухую погоду",
                ],
                "kz": [
                    "Секіретін және ұшатын жәндіктердің шоғыры",
                    "Жеп қойған жапырақ, сабақ, масақ және себет",
                    "Ыстық құрғақ ауада тыңайған жер мен жайылым маңында ошақтар",
                ],
                "en": [
                    "Swarms/groups of hopping and flying insects",
                    "Chewed leaves, stems, ears and heads",
                    "Outbreaks near fallows and pastures in hot dry weather",
                ],
            },
            "action": {
                "ru": "Инсектицидная обработка разрешённым классом (пиретроид/ФОС) по регламенту; срочно оповестить службу защиты растений",
                "kz": "Регламент бойынша рұқсат етілген класпен (пиретроид/ФОҚ) инсектицидтік өңдеу; өсімдік қорғау қызметіне шұғыл хабарлау",
                "en": "Insecticide treatment with an approved class (pyrethroid/OP) per label; notify plant protection service immediately",
            },
            "danger": 3,
            "source": SOURCE,
        },
        {
            "id": "pest_wireworm",
            "crops": ["wheat", "barley", "oats", "sunflower", "rapeseed", "flax"],
            "names": {
                "ru": "Проволочник (личинки щелкунов)",
                "kz": "Сымқұрт (шертуші қоңыз дернәсілі)",
                "en": "Wireworms (click-beetle larvae)",
            },
            "signs": {
                "ru": [
                    "Жёлтые жёсткие червеобразные личинки в почве у семян",
                    "Изъеденные семена и проростки, изреженные всходы",
                    "Увядание молодых растений очагами",
                ],
                "kz": [
                    "Тұқым маңындағы топырақта сары қатты құрт тәрізді дернәсілдер",
                    "Жеп қойған тұқым мен өскін, сиреген көк",
                    "Жас өсімдіктердің ошақтанып солуы",
                ],
                "en": [
                    "Yellow hard worm-like larvae in soil near seeds",
                    "Eaten seeds and seedlings, thinned emergence",
                    "Patchy wilting of young plants",
                ],
            },
            "action": {
                "ru": "Севооборот, обработка почвы против личинок; инсектицидное протравливание семян по регламенту",
                "kz": "Ауыспалы егіс, дернәсілге қарсы топырақ өңдеу; регламент бойынша тұқымды инсектицидпен дәрілеу",
                "en": "Rotation, soil tillage against larvae; insecticidal seed treatment per label",
            },
            "danger": 2,
            "source": SOURCE,
        },
    ],
    "oats": [
        {
            "id": "oats_crown_rust",
            "crops": ["oats"],
            "names": {
                "ru": "Корончатая ржавчина овса",
                "kz": "Сұлының тәж таты",
                "en": "Oats crown rust",
            },
            "signs": {
                "ru": [
                    "Оранжево-жёлтые порошащие пустулы на листьях и влагалищах",
                    "Развивается в тёплую влажную погоду во второй половине лета",
                    "Сильное поражение — щуплое зерно, поле рыжеет",
                ],
                "kz": [
                    "Жапырақ пен қынапта сарғыш ұнтақты пустулалар",
                    "Жаздың екінші жартысында жылы ылғалды ауа райында дамиды",
                    "Қатты зақымданса дән толықсымайды, егістік сарғаяды",
                ],
                "en": [
                    "Orange-yellow powdery pustules on leaves and sheaths",
                    "Develops in warm humid weather in late summer",
                    "Severe attack shrivels grain, field turns rusty",
                ],
            },
            "action": {
                "ru": "Триазольный фунгицид по регламенту при первых пустулах; устойчивые сорта, ранний сев",
                "kz": "Алғашқы пустулаларда регламент бойынша триазолды фунгицид; төзімді сорттар, ерте себу",
                "en": "Triazole fungicide per label at first pustules; resistant varieties, early sowing",
            },
            "danger": 2,
            "source": SOURCE,
        },
    ],
    "rapeseed": [
        {
            "id": "rapeseed_flea",
            "crops": ["rapeseed"],
            "names": {
                "ru": "Крестоцветные блошки на рапсе",
                "kz": "Рапстағы айқышгүлді бүргелер",
                "en": "Flea beetles on rapeseed",
            },
            "signs": {
                "ru": [
                    "Мелкие дырочки-выгрызы на семядолях и первых листьях",
                    "Всходы гибнут в сухую жаркую весну",
                    "Мелкие блестящие чёрные жучки прыгают, если тронуть",
                ],
                "kz": [
                    "Тұқым жарнағы мен алғашқы жапырақтарда ұсақ тесіктер",
                    "Құрғақ ыстық көктемде көк құрып кетеді",
                    "Ұстаса секіретін ұсақ жылтыр қара қоңыздар",
                ],
                "en": [
                    "Tiny shot-holes in cotyledons and first leaves",
                    "Seedlings die in dry hot spring",
                    "Tiny shiny black beetles jump when touched",
                ],
            },
            "action": {
                "ru": "Протравленные семена; в сухую весну — краевая инсектицидная обработка всходов по регламенту, контроль всходов",
                "kz": "Дәріленген тұқым; құрғақ көктемде регламент бойынша көкке жиектік инсектицид, көкті бақылау",
                "en": "Treated seeds; in dry spring — border insecticide on seedlings per label, monitor emergence",
            },
            "danger": 2,
            "source": SOURCE,
        },
        {
            "id": "rapeseed_sclerotinia",
            "crops": ["rapeseed"],
            "names": {
                "ru": "Склеротиниоз (белая гниль) рапса",
                "kz": "Рапстың склеротиниозы (ақ шірік)",
                "en": "Rapeseed sclerotinia (white mold)",
            },
            "signs": {
                "ru": [
                    "Выбеленные стебли с белым налётом в сырое цветение",
                    "Внутри стебля чёрные склероции, стебель полегает",
                    "Очаги полегания после дождей",
                ],
                "kz": [
                    "Ылғал гүлденуде ақ өңезді ағарған сабақтар",
                    "Сабақ ішінде қара склероцийлер, сабақ жатады",
                    "Жаңбырдан кейін жату ошақтары",
                ],
                "en": [
                    "Bleached stems with white mycelium in wet flowering",
                    "Black sclerotia inside stem, lodging",
                    "Lodging patches after rains",
                ],
            },
            "action": {
                "ru": "Фунгицид в цветение по регламенту во влажные годы; севооборот от 4 лет, не сеять после подсолнечника",
                "kz": "Ылғал жылдары гүлденуде регламент бойынша фунгицид; 4 жылдан кем емес ауыспалы егіс, күнбағыстан кейін сеппеу",
                "en": "Fungicide at flowering per label in wet years; rotation of 4+ years, avoid sunflower as predecessor",
            },
            "danger": 2,
            "source": SOURCE,
        },
    ],
    "flax": [
        {
            "id": "flax_wilt",
            "crops": ["flax"],
            "names": {
                "ru": "Фузариозное увядание льна",
                "kz": "Зығырдың фузариозды солуы",
                "en": "Flax fusarium wilt",
            },
            "signs": {
                "ru": [
                    "Пожелтение и поникание верхушек в жаркую сухую погоду",
                    "На срезе стебля бурое кольцо сосудов",
                    "Очаги погибших растений на поле",
                ],
                "kz": [
                    "Ыстық құрғақ ауа райында төбелердің сарғаюы мен салбырауы",
                    "Сабақ кесіндісінде қоңыр түтік сақинасы",
                    "Егістікте өлген өсімдік ошақтары",
                ],
                "en": [
                    "Yellowing and drooping tops in hot dry weather",
                    "Brown vascular ring on stem cross-section",
                    "Patches of dead plants in the field",
                ],
            },
            "action": {
                "ru": "В сезон не лечится: устойчивые сорта и севооборот на будущее; решение о пересеве — с агрономом после осмотра",
                "kz": "Маусымда емделмейді: болашаққа төзімді сорт пен ауыспалы егіс; қайта себу туралы шешім — тексеруден соң агрономмен",
                "en": "No in-season cure: resistant varieties and rotation for the future; replant decision with an agronomist after scouting",
            },
            "danger": 3,
            "source": SOURCE,
        },
    ],
}

# Алиасы культур (ru/kz/en -> ключ GUIDE)
_CROP_ALIASES: dict[str, str] = {
    "wheat": "wheat",
    "spring_wheat": "wheat",
    "spring wheat": "wheat",
    "spring_barley": "barley",
    "spring barley": "barley",
    "пшеница": "wheat",
    "бидай": "wheat",
    "бидайдың": "wheat",
    "barley": "barley",
    "ячмень": "barley",
    "арпа": "barley",
    "арпаның": "barley",
    "sunflower": "sunflower",
    "подсолнечник": "sunflower",
    "күнбағыс": "sunflower",
    "күнбағыстың": "sunflower",
    "common": "common",
    "общие": "common",
    "вредители": "common",
    "oats": "common",
    "овес": "common",
    "овёс": "common",
    "сұлы": "common",
    "rapeseed": "common",
    "рапс": "common",
    "flax": "common",
    "лен": "common",
    "лён": "common",
    "зығыр": "common",
}


def lookup(crop: str) -> list[dict]:
    """Вернуть записи справочника для культуры + общие вредители.

    crop: 'wheat'/'barley'/'sunflower'/'oats'/'rapeseed'/'flax' (или ru/kz алиас).
    Для профильных культур добавляются записи раздела 'common',
    для остальных возвращается раздел 'common'.
    """
    key = (crop or "").strip().lower()
    key = _CROP_ALIASES.get(key, key)
    if key in ("wheat", "barley", "sunflower", "oats", "rapeseed", "flax"):
        return list(GUIDE.get(key, [])) + list(GUIDE.get("common", []))
    if key == "common":
        return list(GUIDE.get("common", []))
    # неизвестная культура — отдаём общих вредителей, а не пустоту
    return list(GUIDE.get("common", []))


def text_of(item: dict, field: str, lang: str):
    """Вложенное поле names/signs/action записи на языке lang (фолбэк ru).

    Схема записей: names:{ru,kz,en} (str), signs:{ru,kz,en} (list),
    action:{ru,kz/en} (str). Плоских ключей name_ru/... в данных нет —
    рендеры (бот, веб) обязаны идти через этот хелпер, иначе None наружу.
    """
    if lang not in ("ru", "kz", "en"):
        lang = "ru"
    v = (item or {}).get(field)
    if isinstance(v, dict):
        return v.get(lang) or v.get("ru")
    return v


# Абиотика (засуха/жара/заморозки): не болезнь и не вредитель, но самая частая
# жалоба. Формат — как записи GUIDE, чтобы рендеры (бот/веб/API) не ветвились.
ABIOTIC: dict[str, dict] = {
    "drought": {
        "id": "abio_drought",
        "crops": ["wheat", "barley", "oats", "sunflower", "rapeseed", "flax"],
        "names": {
            "ru": "Засуха и суховей",
            "kz": "Құрғақшылық және қуаң жел",
            "en": "Drought and dry wind",
        },
        "signs": {
            "ru": [
                "Почва сухая на глубину ладони, всходы вялые к полудню",
                "Дождей нет 2+ недель, жара днём, суховей",
                "Нижние листья скручиваются и подсыхают",
            ],
            "kz": [
                "Топырақ алақан тереңдігінде құрғақ, көк түсте солады",
                "2+ апта жауын жоқ, күндіз ыстық, қуаң жел",
                "Төменгі жапырақтар ширатылып кебеді",
            ],
            "en": [
                "Soil dry to palm depth, seedlings wilt by noon",
                "No rain for 2+ weeks, daytime heat, dry wind",
                "Lower leaves curl and dry out",
            ],
        },
        "action": {
            "ru": "Срочно проверь риск в /alerts и окно в /spray; влагосбережение: сократи обработки почвы, мульчируй; полив — если есть; решение о пересеве — с агрономом",
            "kz": "Шұғыл /alerts қаупін және /spray терезесін тексер; ылғал үнемдеу: топырақ өңдеуді азайт; суару — болса; қайта себу — агрономмен",
            "en": "Urgently check risk in /alerts and window in /spray; save moisture: cut tillage, mulch; irrigate if available; replant decision with an agronomist",
        },
        "danger": 3,
        "source": SOURCE,
    },
    "heat": {
        "id": "abio_heat",
        "crops": ["wheat", "barley", "oats", "sunflower", "rapeseed", "flax"],
        "names": {
            "ru": "Жара выше нормы",
            "kz": "Нормадан жоғары ыстық",
            "en": "Above-normal heat",
        },
        "signs": {
            "ru": [
                "Днём 30°+, ночью не остывает",
                "Цветение/налив совпали с жарой",
                "Растения вялые даже утром",
            ],
            "kz": [
                "Күндіз 30°+, түнде салқындамайды",
                "Гүлдену/толысу ыстыққа сәйкес келді",
                "Өсімдік таңертең де солғын",
            ],
            "en": [
                "Daytime 30°C+, no cooling at night",
                "Flowering/grain filling coincided with heat",
                "Plants wilted even in the morning",
            ],
        },
        "action": {
            "ru": "Работы — рано утром/вечером; опрыскивания только в окно /spray (ветер<5, без дождя, 10–25°C); сохрани влагу, не трогай почву в зной",
            "kz": "Жұмыстар — таңертең/кешке; бүрку тек /spray терезесінде (жел<5, жауынсыз, 10–25°C); ылғалды сақта, ыстықта топырақты қозғама",
            "en": "Work early morning/evening; spray only in the /spray window (wind<5, no rain, 10–25°C); keep moisture, skip tillage in heat",
        },
        "danger": 2,
        "source": SOURCE,
    },
    "frost": {
        "id": "abio_frost",
        "crops": ["wheat", "barley", "oats", "sunflower", "rapeseed", "flax"],
        "names": {
            "ru": "Заморозки",
            "kz": "Үсік",
            "en": "Frost",
        },
        "signs": {
            "ru": [
                "Ночью около 0° и ниже, иней на всходах",
                "Листья стекловидные, потом белеют",
                "Пострадали низины и края поля",
            ],
            "kz": [
                "Түнде 0° маңы және төмен, көкте қырау",
                "Жапырақ шыныдай, соңыра ағарады",
                "Ойпат пен егіс шеті зардап шекті",
            ],
            "en": [
                "Night near/below 0°C, rime on seedlings",
                "Leaves glassy, then whiten",
                "Low spots and field edges hit",
            ],
        },
        "action": {
            "ru": "Подожди 2–3 дня: точка роста жива — отойдёт; проверь /alerts на повтор; погибшие очаги — подсев после осмотра с агрономом",
            "kz": "2–3 күн күт: өсу нүктесі тірі болса — қалпына келеді; қайталануын /alerts-тен қара; өлген ошақтар — тексеруден соң агрономмен үстеп себу",
            "en": "Wait 2–3 days: if the growing point is alive it recovers; re-check /alerts; dead patches — overseed after scouting with an agronomist",
        },
        "danger": 2,
        "source": SOURCE,
    },
}

# Жалоба -> ключ ABIOTIC (все языки сразу — пользователь пишет как удобно).
_ABIO_ALIASES: dict[str, list[str]] = {
    "drought": ["засух", "сушь", "суховей", "сухо", "нет дожд", "без дожд",
                "құрғақ", "қуаң", "жауын жоқ", "drought", "dry spell", "no rain"],
    "heat": ["жар", "пекло", "зной", "ыстық", "аптап", "heat", "hot"],
    "frost": ["замороз", "мороз", "холод", "үсік", "аяз", "суық", "frost", "freeze"],
    "pests": ["вредит", "насеком", "жук", "гусениц", "тля", "зиянкес",
              "жәндік", "қоңыз", "pest", "insect", "bug", "aphid"],
}


def _all_entries() -> list[dict]:
    seen: dict[str, dict] = {}
    for section in GUIDE.values():
        for e in section:
            if isinstance(e, dict) and e.get("id") not in seen:
                seen[e["id"]] = e
    return list(seen.values())


def search_guide(query: str, lang: str = "ru", top: int = 3) -> list[dict]:
    """Жалоба словами -> релевантные записи (вместо первых N справочника).

    1) Прямое попадание в абиотику (засуха/жара/заморозки/вредители вообще).
    2) Иначе скоринг по всем записям: совпадение в names (+3) / id (+2) /
       signs+action (+1) — тексты всех 3 языков сразу, язык жалобы не важен.
    Пустой запрос или нулевой скор -> [] (вызывающий показывает подсказку).
    """
    if lang not in ("ru", "kz", "en"):
        lang = "ru"
    q = (query or "").strip().lower()
    if not q:
        return []
    for pid, aliases in _ABIO_ALIASES.items():
        if any(a in q for a in aliases):
            if pid == "pests":
                return [e for e in _all_entries()
                        if str(e.get("id") or "").startswith("pest_")][:max(1, top)]
            return [ABIOTIC[pid]]
    scored: list[tuple[int, dict]] = []
    for e in _all_entries():
        score = 0
        texts_names: list[str] = []
        texts_body: list[str] = []
        for lg in ("ru", "kz", "en"):
            nm = (e.get("names") or {}).get(lg) or ""
            texts_names.append(str(nm).lower())
            for f in ("signs", "action"):
                v = (e.get(f) or {}).get(lg)
                if isinstance(v, list):
                    texts_body.extend(str(x).lower() for x in v)
                elif v:
                    texts_body.append(str(v).lower())
        if any(q in t for t in texts_names if t):
            score += 3
        if q and q in str(e.get("id", "")).lower():
            score += 2
        score += sum(1 for t in texts_body if q and t and q in t)
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda r: -r[0])
    return [e for _, e in scored[:max(1, top)]]


__all__ = ["GUIDE", "SOURCE", "lookup", "text_of", "ABIOTIC", "search_guide"]
