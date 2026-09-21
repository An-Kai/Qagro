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

    crop: 'wheat' | 'barley' | 'sunflower' (или ru/kz алиас).
    Для профильных культур добавляются записи раздела 'common',
    для остальных возвращается раздел 'common'.
    """
    key = (crop or "").strip().lower()
    key = _CROP_ALIASES.get(key, key)
    if key in ("wheat", "barley", "sunflower"):
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


__all__ = ["GUIDE", "SOURCE", "lookup", "text_of"]
