import asyncio
import html
import json
import logging
import os
import random
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from telegram import ChatMember, MessageEntity, Update, User
from telegram.error import TelegramError
from telegram.constants import ChatType, MessageEntityType
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from content import copy_random_gif_to_chat
from i18n import detect_lang
from ip_scan import (
    format_ip_dossier_caption,
    format_ip_dossier_profile_block,
    is_v2_ip_dossier,
    owner_classified_dossier_v2,
)

logger = logging.getLogger(__name__)

# Якщо args/entities «зламались», витягуємо нік з тексту: /ip @nick або /ip nick
_IP_USERNAME_FROM_TEXT = re.compile(
    r"^/ip(?:@[\w]+)?\s+(?:@)?([A-Za-z0-9_]{4,32})\b",
    re.IGNORECASE | re.UNICODE,
)
_IP_USERNAME_ANYWHERE = re.compile(
    r"/ip(?:@[\w]+)?\s+(?:@)?([A-Za-z0-9_]{4,32})\b",
    re.IGNORECASE | re.UNICODE,
)


def _chat_is_private_user(chat) -> bool:
    """У Bot API приватний чат із людиною має type private (інколи str, інколи enum)."""
    ct = getattr(chat, "type", None)
    if ct == ChatType.PRIVATE:
        return True
    if isinstance(ct, str) and ct.lower() == "private":
        return True
    val = getattr(ct, "value", None)
    if isinstance(val, str) and val.lower() == "private":
        return True
    return "private" in str(ct).lower()


def _chat_represents_user(chat) -> bool:
    """
    Чи це профіль людини з get_chat(@username).
    Інколи type не збігається з «private» через версію PTB/API — дивимось ще на поля.
    """
    if _chat_is_private_user(chat):
        return True
    ct = getattr(chat, "type", None)
    if ct in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        return False
    if isinstance(ct, str) and ct.lower() in ("group", "supergroup", "channel"):
        return False
    if getattr(chat, "title", None):
        return False
    return bool(getattr(chat, "first_name", None) or getattr(chat, "username", None))


def _entity_is_mention(ent) -> bool:
    ts = str(ent.type).lower()
    if "text_mention" in ts:
        return False
    if ent.type == MessageEntityType.MENTION:
        return True
    return ts in ("mention", "messageentitytype.mention")


def _entity_is_text_mention(ent) -> bool:
    if ent.type == MessageEntityType.TEXT_MENTION:
        return True
    return "text_mention" in str(ent.type).lower()


def _resolve_bot_state_db_path() -> Path:
    """Локально — bot_state.db у корені проєкту; у хмарі задай BOT_STATE_DB_PATH (напр. /data/bot_state.db + volume)."""
    root = Path(__file__).resolve().parent.parent
    raw = os.getenv("BOT_STATE_DB_PATH", "").strip()
    if not raw:
        return root / "bot_state.db"
    p = Path(raw)
    return p if p.is_absolute() else (root / p).resolve()


DB_PATH = _resolve_bot_state_db_path()
FOODS_FILE = Path(__file__).resolve().parent.parent / "poop_foods.txt"
EAT_COOLDOWN_SEC = 20 * 60
FIRST_POOP_DELAY_SEC = 60 * 60
EAT_COOLDOWN_MIN = EAT_COOLDOWN_SEC // 60
POOP_URGE_DELAY_MIN = FIRST_POOP_DELAY_SEC // 60
SCHEDULER_TICK_SEC = 20
BOT_OWNER_USERNAME = "rofl3121"
KAKAPAIR_COOLDOWN_SEC = 55


@dataclass(frozen=True)
class Food:
    ru: str
    uk: str
    bonus: int
    tag: str


FOODS: list[Food] = [
    Food("пиццу с чили", "піцу з чилі", 35, "spicy"),
    Food("суши с васаби", "суші з васабі", 28, "spicy"),
    Food("тарелку борща", "тарілку борщу", 12, "normal"),
    Food("шаурму с двойным соусом", "шаурму з подвійним соусом", 24, "normal"),
    Food("чебурек из автомата", "чебурек з автомата", 26, "weird"),
    Food("энергетик из-под кровати", "енергетик з-під ліжка", 40, "weird"),
    Food("лапшу быстрого выживания", "локшину швидкого виживання", 17, "normal"),
    Food("тройной бургер с огнем", "потрійний бургер з вогнем", 30, "spicy"),
    Food("подозрительный кефир", "підозрілий кефір", 34, "weird"),
    Food("дошик и маринованный перец", "дошик і маринований перець", 33, "spicy"),
    Food("колу и солёный огурец", "колу і солоний огірок", 20, "weird"),
    Food("дюжину острых крылышек", "дюжину гострих крилець", 44, "spicy"),
    Food("панкейки с кетчупом", "панкейки з кетчупом", 25, "weird"),
    Food("биткоин 2021 года (на вкус как боль)", "біткоїн 2021 року (на смак як біль)", 60, "inedible"),
    Food("твит Илона Маска", "твіт Ілона Маска", 55, "inedible"),
    Food("носки админа", "шкарпетки адміна", 62, "inedible"),
    Food("зарядку от нокии", "зарядку від нокії", 66, "inedible"),
    Food("кусок бетонной романтики", "шмат бетонної романтики", 64, "inedible"),
    Food("протеиновый коктейль с хреном", "протеїновий коктейль з хроном", 38, "spicy"),
    Food("салат с майонезом и карри", "салат з майонезом і карі", 31, "spicy"),
    Food("манты с аджикой", "манти з аджикою", 29, "spicy"),
    Food("оливье после трёх праздников", "олів'є після трьох свят", 36, "weird"),
    Food("кашу с энергетиком", "кашу з енергетиком", 27, "weird"),
    Food("хот-дог с тройной горчицей", "хот-дог з потрійною гірчицею", 32, "spicy"),
    Food("буррито апокалипсиса", "буріто апокаліпсису", 45, "spicy"),
    Food("пельмени с острым маслом", "пельмені з гострою олією", 22, "spicy"),
    Food("йогурт из неизвестного измерения", "йогурт з невідомого виміру", 41, "weird"),
    Food("солёную карамель и чеснок", "солону карамель і часник", 34, "weird"),
    Food("чипсы с урановым вкусом", "чипси з урановим смаком", 58, "inedible"),
    Food("пломбир с перцем", "пломбір з перцем", 23, "spicy"),
    Food("сырный вулкан", "сирний вулкан", 26, "normal"),
    Food("тройной латте и острый тако", "потрійне латте і гостре тако", 35, "spicy"),
    Food("банку сгущенки и чили", "банку згущеного молока і чилі", 33, "spicy"),
]

# Актуальные отсылки (Italian brainrot, TikTok и т.п.) — одна случайная строка к результату какания.
POOP_MEME_LINES: list[tuple[str, str]] = [
    (
        "🥁 Tung Tung Tung Sahur… это был не будильник, это метаболизм.",
        "🥁 Tung Tung Tung Sahur… це був не будильник, а метаболізм.",
    ),
    (
        "☕ Балерина капучино поставила плие — выход с пенкой и без суеты.",
        "☕ Балерина капучино зробила пліє — вихід із пінкою і без метушні.",
    ),
    (
        "🤫 Тихо, не спеша, без суеты… именно так и задумывался этот релиз.",
        "🤫 Тихо, не поспішаючи, без метушні… саме так і задумувався цей реліз.",
    ),
    (
        "🐊 Бомбардиро Крокодило оценил бы траекторию — чистый плановый заход.",
        "🐊 Бомбардиро Крокодило оцінив би траєкторію — чистий плановий захід.",
    ),
    (
        "🦐 Тралалело Тралала — но звук на этот раз с правильной стороны.",
        "🦐 Тралалело Тралала — але звук цього разу з правильного боку.",
    ),
    (
        "🐸 Лирили Ларила: природа взяла микрофон, остальное — история.",
        "🐸 Лірілі Ларіла: природа взяла мікрофон, решта — історія.",
    ),
    (
        "🦛 Brr Brr Patapim — ритм соблюдён, пульс в норме, чат в шоке.",
        "🦛 Brr Brr Patapim — ритм витримано, пульс у нормі, чат у шоці.",
    ),
    (
        "🧠 Italian brainrot, но ЖКТ выдал лор канонический.",
        "🧠 Italian brainrot, але ЖКТ видав канонічний лор.",
    ),
    (
        "🍌 Чипи чипи чапа чапа — только это уже не про обезьянку.",
        "🍌 Чипі чипі чапа чапа — тільки це вже не про мавпочку.",
    ),
    (
        "🦈 Трилли Трилла Трилло Тралала — дуэль окончена, победила физика.",
        "🦈 Триллі Трилла Трилло Тралала — дуель закінчена, перемогла фізика.",
    ),
    (
        "🪵 Полено с битой не пришло — зато пришло осознание.",
        "🪵 Поліно з битою не прийшло — зате прийшло усвідомлення.",
    ),
    (
        "📳 Это не вибрация телефона — это твой кишечник в тренде TikTok.",
        "📳 Це не вібрація телефону — це твій кишківник у тренді TikTok.",
    ),
    (
        "🎺 Капучино ассасино не участвовал, но атмосфера та же.",
        "🎺 Капучіно ассасіно не брав участі, але атмосфера та сама.",
    ),
    (
        "🍝 Сигма? Нет. Спагетти? Тоже нет. Только честный перформанс.",
        "🍝 Сигма? Ні. Спагеті? Теж ні. Лише чесний перформанс.",
    ),
    (
        "🧊 Frigo Camelo хранил холод, а ты — накопил проценты.",
        "🧊 Frigo Camelo зберігав холод, а ти — накопичив відсотки.",
    ),
]


def _random_poop_meme_line(lang: str) -> str:
    ru, uk = random.choice(POOP_MEME_LINES)
    return uk if lang == "uk" else ru


OBOSRAT_LINES_RU: list[str] = [
    "💩 Вас обосрал {attacker}. По счётчику уже {count}.",
    "💩 {attacker} обосрал вас так уверенно, будто это была главная миссия дня. Всего: {count}.",
    "💩 {attacker} снова в деле: каловая драма на ваших щёчках и {count} отметок в личной истории.",
    "💩 Вас настиг выброс от {attacker}. Слёзы обиды, румянец стыда и счётчик: {count}.",
    "💩 {attacker} оформил вам эпизод отчаяния с ароматом кармы. Всего обосрано: {count}.",
    "💩 {attacker} выдал настолько плотный перформанс, что щёчки помнят каждую секунду. Счёт: {count}.",
    "💩 Вас эффектно накрыло от {attacker}. Горькие слёзы, печальный вайб и ровно {count} попаданий.",
    "💩 {attacker} устроил вам грязный сюжетный поворот. В статистике теперь: {count}.",
    "💩 {attacker} добавил вам ещё одну главу в хроники унижения. Итого: {count}.",
    "💩 Вас обосрал {attacker}, а достоинство ушло в перезагрузку. По счётчику: {count}.",
]

OBOSRAT_LINES_UK: list[str] = [
    "💩 Вас обісрав {attacker}. За лічильником уже {count}.",
    "💩 {attacker} обісрав вас так впевнено, ніби це була головна місія дня. Всього: {count}.",
    "💩 {attacker} знову в ділі: калова драма на ваших щічках і {count} відміток в історії.",
    "💩 Вас наздогнав викид від {attacker}. Сльози образи, рум'янець сорому і лічильник: {count}.",
    "💩 {attacker} оформив вам епізод відчаю з ароматом карми. Всього обісрано: {count}.",
    "💩 {attacker} видав настільки щільний перформанс, що щічки запам'ятали кожну секунду. Рахунок: {count}.",
    "💩 Вас ефектно накрило від {attacker}. Гіркі сльози, сумний вайб і рівно {count} влучань.",
    "💩 {attacker} влаштував вам брудний сюжетний поворот. У статистиці тепер: {count}.",
    "💩 {attacker} додав вам ще одну главу в хроніки приниження. Разом: {count}.",
    "💩 Вас обісрав {attacker}, а гідність пішла в перезавантаження. За лічильником: {count}.",
]


def _load_foods_from_file() -> list[Food]:
    """
    Format per line in poop_foods.txt:
    ru_text|uk_text|bonus|tag
    """
    if not FOODS_FILE.exists():
        return []
    loaded: list[Food] = []
    for raw in FOODS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            continue
        ru_text, uk_text, bonus_raw, tag = parts
        try:
            bonus = int(bonus_raw)
        except ValueError:
            continue
        if tag not in {"normal", "weird", "spicy", "inedible"}:
            continue
        loaded.append(Food(ru=ru_text, uk=uk_text, bonus=bonus, tag=tag))
    return loaded


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _normalize_shit_received(raw: object) -> dict:
    if not raw:
        return {"counts": {}, "names": {}}
    if isinstance(raw, dict) and "counts" in raw:
        counts = raw.get("counts") or {}
        names = raw.get("names") or {}
        return {
            "counts": {str(k): int(v) for k, v in counts.items()},
            "names": {str(k): str(v) for k, v in names.items()},
        }
    if isinstance(raw, dict) and raw and all(isinstance(v, int) for v in raw.values()):
        return {"counts": {str(k): int(v) for k, v in raw.items()}, "names": {}}
    return {"counts": {}, "names": {}}


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS poop_profiles (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                lang TEXT NOT NULL DEFAULT 'ru',
                last_eat_ts REAL NOT NULL DEFAULT 0,
                stomach_json TEXT NOT NULL DEFAULT '[]',
                inventory_json TEXT NOT NULL DEFAULT '{}',
                eat_count INTEGER NOT NULL DEFAULT 0,
                poop_count INTEGER NOT NULL DEFAULT 0,
                total_poop_power REAL NOT NULL DEFAULT 0,
                best_poop_power REAL NOT NULL DEFAULT 0,
                achievements_json TEXT NOT NULL DEFAULT '{}',
                shit_received_json TEXT NOT NULL DEFAULT '{}',
                shit_given_json TEXT NOT NULL DEFAULT '{}',
                last_obosrat_at_eat_count INTEGER NOT NULL DEFAULT -1,
                next_poop_ts REAL
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(poop_profiles)").fetchall()
        }
        if "achievements_json" not in columns:
            conn.execute(
                "ALTER TABLE poop_profiles ADD COLUMN achievements_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "inventory_json" not in columns:
            conn.execute(
                "ALTER TABLE poop_profiles ADD COLUMN inventory_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "eat_count" not in columns:
            conn.execute(
                "ALTER TABLE poop_profiles ADD COLUMN eat_count INTEGER NOT NULL DEFAULT 0"
            )
        if "shit_received_json" not in columns:
            conn.execute(
                "ALTER TABLE poop_profiles ADD COLUMN shit_received_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "last_obosrat_at_eat_count" not in columns:
            conn.execute(
                "ALTER TABLE poop_profiles ADD COLUMN last_obosrat_at_eat_count INTEGER NOT NULL DEFAULT -1"
            )
        if "shit_given_json" not in columns:
            conn.execute(
                "ALTER TABLE poop_profiles ADD COLUMN shit_given_json TEXT NOT NULL DEFAULT '{}'"
            )


def _load_profile(user_id: int, chat_id: int, lang: str) -> dict:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT user_id, chat_id, lang, last_eat_ts, stomach_json, eat_count, poop_count,
                   inventory_json, total_poop_power, best_poop_power, achievements_json,
                   shit_received_json, shit_given_json, last_obosrat_at_eat_count, next_poop_ts
            FROM poop_profiles WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row:
            return {
                "user_id": row[0],
                "chat_id": row[1],
                "lang": row[2],
                "last_eat_ts": row[3],
                "stomach": json.loads(row[4]),
                "eat_count": row[5],
                "poop_count": row[6],
                "inventory": json.loads(row[7] or "{}"),
                "total_poop_power": row[8],
                "best_poop_power": row[9],
                "achievements": json.loads(row[10] or "{}"),
                "shit_received": _normalize_shit_received(json.loads(row[11] or "{}")),
                "shit_given": _normalize_shit_received(json.loads(row[12] or "{}")),
                "last_obosrat_at_eat_count": row[13],
                "next_poop_ts": row[14],
            }
        conn.execute(
            """
            INSERT INTO poop_profiles (user_id, chat_id, lang)
            VALUES (?, ?, ?)
            """,
            (user_id, chat_id, lang),
        )
    return {
        "user_id": user_id,
        "chat_id": chat_id,
        "lang": lang,
        "last_eat_ts": 0.0,
        "stomach": [],
        "eat_count": 0,
        "poop_count": 0,
        "inventory": {},
        "total_poop_power": 0.0,
        "best_poop_power": 0.0,
        "achievements": {"unlocked": [], "counts": {}},
        "shit_received": {"counts": {}, "names": {}},
        "shit_given": {"counts": {}, "names": {}},
        "last_obosrat_at_eat_count": -1,
        "next_poop_ts": None,
    }


def _save_profile(profile: dict) -> None:
    with _conn() as conn:
        conn.execute(
            """
            UPDATE poop_profiles
            SET chat_id = ?, lang = ?, last_eat_ts = ?, stomach_json = ?, eat_count = ?, poop_count = ?,
                inventory_json = ?, total_poop_power = ?, best_poop_power = ?, achievements_json = ?,
                shit_received_json = ?, shit_given_json = ?, last_obosrat_at_eat_count = ?, next_poop_ts = ?
            WHERE user_id = ?
            """,
            (
                profile["chat_id"],
                profile["lang"],
                profile["last_eat_ts"],
                json.dumps(profile["stomach"], ensure_ascii=False),
                profile.get("eat_count", 0),
                profile["poop_count"],
                json.dumps(profile.get("inventory", {}), ensure_ascii=False),
                profile["total_poop_power"],
                profile["best_poop_power"],
                json.dumps(profile.get("achievements", {"unlocked": [], "counts": {}}), ensure_ascii=False),
                json.dumps(profile.get("shit_received", {"counts": {}, "names": {}}), ensure_ascii=False),
                json.dumps(profile.get("shit_given", {"counts": {}, "names": {}}), ensure_ascii=False),
                int(profile.get("last_obosrat_at_eat_count", -1)),
                profile["next_poop_ts"],
                profile["user_id"],
            ),
        )


def _combo_text(lang: str, tags: list[str]) -> str:
    if "spicy" in tags and "inedible" in tags:
        return (
            "Комбо: огненно-металлическая буря в кишечнике."
            if lang == "ru"
            else "Комбо: вогняно-металева буря в кишківнику."
        )
    if "weird" in tags and "spicy" in tags:
        return (
            "Комбо: токсичная шипучка и ядерный рикошет."
            if lang == "ru"
            else "Комбо: токсична шипучка та ядерний рикошет."
        )
    return "Комбо: дикая турбулентность." if lang == "ru" else "Комбо: дика турбулентність."


def _rank(lang: str, avg: float) -> str:
    if avg >= 180:
        return "космический разрушитель" if lang == "ru" else "космічний руйнівник"
    if avg >= 130:
        return "легенда канализации" if lang == "ru" else "легенда каналізації"
    if avg >= 90:
        return "мастер шторма" if lang == "ru" else "майстер шторму"
    return "скромный хлопок" if lang == "ru" else "скромний хлопок"


def _result_line(lang: str, power: float) -> str:
    if power < 60:
        return (
            "Почти тишина. Организм сделал вид, что ничего не было."
            if lang == "ru"
            else "Майже тиша. Організм зробив вигляд, що нічого не було."
        )
    if power < 110:
        return (
            "Средний гром: чат выжил, но атмосфера уже не та."
            if lang == "ru"
            else "Середній грім: чат вижив, але атмосфера вже не та."
        )
    if power < 170:
        return (
            "Жесткий выброс! Окна дрожат, модераторы в панике."
            if lang == "ru"
            else "Жорсткий викид! Вікна дрижать, модератори в паніці."
        )
    return (
        "Апокалипсис! Даже Марс просит санитарный день."
        if lang == "ru"
        else "Апокаліпсис! Навіть Марс просить санітарний день."
    )


def _virtual_weight(eat_count: int) -> tuple[float, int]:
    # 1 eat = 0.5 kg.
    kg = max(0.0, float(eat_count) * 0.5)
    meter = max(0, min(999999, int(kg * 10)))
    return kg, meter


def _weight_title(lang: str, meter: int) -> str:
    if meter < 1000:
        return "ты пустота" if lang == "ru" else "ти порожнеча"
    if meter < 10000:
        return "весишь как самокат с турбиной" if lang == "ru" else "важиш як самокат з турбіною"
    if meter < 50000:
        return "весишь как рынок шаурмы в час пик" if lang == "ru" else "важиш як ринок шаурми в годину пік"
    if meter < 150000:
        return "весишь как промышленный район" if lang == "ru" else "важиш як промисловий район"
    if meter < 350000:
        return "весишь как маленькая область" if lang == "ru" else "важиш як маленька область"
    if meter < 700000:
        return "весишь как автономная республика мемов" if lang == "ru" else "важиш як автономна республіка мемів"
    return "весишь как целая страна хаоса" if lang == "ru" else "важиш як ціла країна хаосу"


def _weight_line(lang: str, eat_count: int) -> str:
    kg, meter = _virtual_weight(eat_count)
    _ = meter  # keep meter calculation for future balancing
    return f"⚖️ Вес: {kg:.1f} кг" if lang == "ru" else f"⚖️ Вага: {kg:.1f} кг"


def _stomach_accumulated_power(stomach: list[dict]) -> float:
    """Примерная оценка диапазона по текущему числу приемов пищи (1..3)."""
    size = max(0, min(3, len(stomach)))
    if size <= 0:
        return 0.0
    if size == 1:
        return 10.0
    if size == 2:
        return 50.0
    return 100.0


def _resolve_poop_power_from_stomach(stomach: list[dict], forced: bool = False) -> float:
    """
    Правило по числу приемов пищи в цикле:
    - 1 прием: 1..10%
    - 2 приема: 1..50%
    - 3 приема: 1..100%
    + 0.1% шанс на результат >100%
    """
    if not stomach:
        return 0.0
    size = max(1, min(3, len(stomach)))
    upper = 10.0 if size == 1 else (50.0 if size == 2 else 100.0)
    power = random.uniform(1.0, upper)

    # 0.1% шанс на сверхрезультат >100
    if random.random() < 0.001:
        power = random.uniform(101.0, 200.0)

    if forced:
        power = min(200.0, power + 5.0)

    return max(0.0, min(200.0, power))


def _update_achievements(profile: dict, power: float) -> list[str]:
    data = profile.get("achievements") or {}
    unlocked = set(data.get("unlocked", []))
    counts = data.get("counts", {})

    if power > 100:
        counts["over_100"] = int(counts.get("over_100", 0)) + 1
    if power >= 150:
        counts["over_150"] = int(counts.get("over_150", 0)) + 1
    if power >= 180:
        counts["over_180"] = int(counts.get("over_180", 0)) + 1
    if power >= 200:
        counts["jackpot_200"] = int(counts.get("jackpot_200", 0)) + 1

    newly_unlocked: list[str] = []
    checks = [
        ("over_100_once", counts.get("over_100", 0) >= 1),
        ("over_150_once", counts.get("over_150", 0) >= 1),
        ("over_180_once", counts.get("over_180", 0) >= 1),
        ("jackpot_200_once", counts.get("jackpot_200", 0) >= 1),
    ]
    for key, ok in checks:
        if ok and key not in unlocked:
            unlocked.add(key)
            newly_unlocked.append(key)

    poop_count = int(profile.get("poop_count", 0))
    for key, needed in (
        ("poop_1", 1),
        ("poop_100", 100),
        ("poop_200", 200),
        ("poop_666", 666),
        ("poop_1000", 1000),
        ("poop_2000", 2000),
    ):
        if poop_count >= needed and key not in unlocked:
            unlocked.add(key)
            newly_unlocked.append(key)

    if power >= 120 and "power_120_once" not in unlocked:
        unlocked.add("power_120_once")
        newly_unlocked.append("power_120_once")

    profile["achievements"] = {
        "unlocked": sorted(unlocked),
        "counts": counts,
    }
    return newly_unlocked


def _achievement_labels(lang: str, keys: list[str]) -> str:
    mapping_ru = {
        "over_100_once": "⚡ Первый прорыв 100%+",
        "power_120_once": "🧪 Редкий выброс 120%+",
        "over_150_once": "🔥 Шторм 150%+",
        "over_180_once": "☢ Перегрузка 180%+",
        "jackpot_200_once": "👑 Легендарный 200.0%",
        "poop_1": "💩 Первая какашка",
        "poop_100": "💯 Сотка каканий",
        "poop_200": "🏭 Двести каканий",
        "poop_666": "😈 Число хаоса: 666",
        "poop_1000": "🏆 Тысячник канализации",
        "poop_2000": "🚀 За гранью: 2000+",
        "pill_used_once": "💊 Использовал таблетки",
        "rare_food_once": "🍀 Съел очень редкую еду",
        "shit_by_5_unique": "🎯 Обосран сразу 5 людьми",
    }
    mapping_uk = {
        "over_100_once": "⚡ Перший прорив 100%+",
        "power_120_once": "🧪 Рідкісний викид 120%+",
        "over_150_once": "🔥 Шторм 150%+",
        "over_180_once": "☢ Перевантаження 180%+",
        "jackpot_200_once": "👑 Легендарний 200.0%",
        "poop_1": "💩 Перша какашка",
        "poop_100": "💯 Сотня какань",
        "poop_200": "🏭 Двісті какань",
        "poop_666": "😈 Число хаосу: 666",
        "poop_1000": "🏆 Тисячник каналізації",
        "poop_2000": "🚀 За межею: 2000+",
        "pill_used_once": "💊 Використав таблетки",
        "rare_food_once": "🍀 З'їв дуже рідкісну їжу",
        "shit_by_5_unique": "🎯 Обісраний одразу 5 людьми",
    }
    m = mapping_uk if lang == "uk" else mapping_ru
    return "\n".join(m.get(k, k) for k in keys)


def _unlock_direct_achievement(profile: dict, key: str) -> bool:
    data = profile.get("achievements") or {}
    unlocked = set(data.get("unlocked", []))
    if key in unlocked:
        return False
    unlocked.add(key)
    profile["achievements"] = {
        "unlocked": sorted(unlocked),
        "counts": data.get("counts", {}),
    }
    return True


def _stomach_status_line(lang: str, stomach: list[dict]) -> str:
    size = len(stomach)
    if size <= 0:
        return "🫃 Желудок: пусто" if lang == "ru" else "🫃 Шлунок: порожньо"
    if size == 1:
        return "🫃 Желудок: что-то булькает" if lang == "ru" else "🫃 Шлунок: щось булькає"
    return "🫃 Желудок: полон сюрпризов" if lang == "ru" else "🫃 Шлунок: повний сюрпризів"


def _stomach_poop_range_line(lang: str, stomach: list[dict]) -> str:
    size = len(stomach)
    if size <= 0:
        return (
            "📉 Вероятный процент испражнения: 0% (желудок пуст)."
            if lang == "ru"
            else "📉 Ймовірний відсоток какання: 0% (шлунок порожній)."
        )
    if size == 1:
        base = "1-10%"
    elif size == 2:
        base = "1-50%"
    else:
        base = "1-100%"
    return (
        f"📉 Вероятный процент испражнения: {base}, и 0.1% шанс на 101-200%."
        if lang == "ru"
        else f"📉 Ймовірний відсоток какання: {base}, і 0.1% шанс на 101-200%."
    )


def _inv_add(profile: dict, key: str, amount: int = 1) -> None:
    inv = profile.get("inventory") or {}
    inv[key] = int(inv.get(key, 0)) + amount
    profile["inventory"] = inv


def _food_to_inv_dict(food: Food) -> dict:
    return {"ru": food.ru, "uk": food.uk, "bonus": int(food.bonus), "tag": food.tag}


def _food_inventory(profile: dict) -> list[dict]:
    inv = profile.get("inventory") or {}
    raw = inv.get("food_items") or []
    if not isinstance(raw, list):
        return []
    normalized: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ru = str(item.get("ru", "")).strip()
        uk = str(item.get("uk", "")).strip()
        tag = str(item.get("tag", "normal")).strip()
        try:
            bonus = int(item.get("bonus", 0))
        except (TypeError, ValueError):
            bonus = 0
        if not ru or not uk:
            continue
        if tag not in {"normal", "weird", "spicy", "inedible"}:
            tag = "normal"
        normalized.append({"ru": ru, "uk": uk, "bonus": bonus, "tag": tag})
    return normalized


def _set_food_inventory(profile: dict, foods: list[dict]) -> None:
    inv = profile.get("inventory") or {}
    inv["food_items"] = foods
    profile["inventory"] = inv


def _grant_food_to_inventory(profile: dict, food: Food) -> None:
    foods = _food_inventory(profile)
    foods.append(_food_to_inv_dict(food))
    _set_food_inventory(profile, foods)


def _take_inventory_food(profile: dict) -> Optional[dict]:
    foods = _food_inventory(profile)
    if not foods:
        return None
    idx = random.randrange(len(foods))
    picked = foods.pop(idx)
    _set_food_inventory(profile, foods)
    return picked


def _ip_dossier_profile_section(
    lang: str,
    profile: dict,
    user_display: str,
    *,
    force_owner_classified: bool = False,
) -> str:
    """Блок IP-досье в том же порядке полей, что на карточке /ip (скрин «Об'єкт / Ім'я / …»)."""
    if force_owner_classified:
        return format_ip_dossier_profile_block(
            lang, owner_classified_dossier_v2(lang), user_display
        )
    inv = profile.get("inventory") or {}
    _d = inv.get("ip_dossier")
    if isinstance(_d, dict) and is_v2_ip_dossier(_d):
        return format_ip_dossier_profile_block(lang, _d, user_display)
    if isinstance(_d, dict) and str(_d.get("text", "")).strip():
        return (
            "📇 Досье (старый формат): /ip_reset → /ip"
            if lang == "ru"
            else "📇 Досьє (старий формат): /ip_reset → /ip"
        )
    return ""


def _inventory_block(lang: str, profile: dict) -> str:
    inv = profile.get("inventory") or {}
    charcoal = int(inv.get("stomach_charcoal", 0))
    foods = _food_inventory(profile)
    if charcoal <= 0 and not foods:
        return "🎒 Инвентарь: пусто" if lang == "ru" else "🎒 Інвентар: порожньо"
    parts: list[str] = []
    if charcoal > 0:
        parts.append(
            f"Уголь для желудка x{charcoal}"
            if lang == "ru"
            else f"Вугілля для шлунка x{charcoal}"
        )
    if foods:
        preview = ", ".join((f["uk"] if lang == "uk" else f["ru"]) for f in foods[:3])
        if len(foods) > 3:
            preview += ", ..."
        parts.append(
            f"Еда: {len(foods)} шт ({preview})"
            if lang == "ru"
            else f"Їжа: {len(foods)} шт ({preview})"
        )
    else:
        parts.append("Еда: пусто" if lang == "ru" else "Їжа: порожньо")
    header = "🎒 Инвентарь:" if lang == "ru" else "🎒 Інвентар:"
    return header + "\n" + "\n".join(parts)


def _display_name(user: User) -> str:
    if user.username:
        return f"@{user.username}"
    name = (user.first_name or "").strip()
    if user.last_name:
        name = f"{name} {user.last_name}".strip()
    return name or str(user.id)


def _shit_top_block(lang: str, shit_received: dict, limit: int = 10) -> str:
    data = _normalize_shit_received(shit_received)
    counts = data.get("counts") or {}
    names = data.get("names") or {}
    if not counts:
        return (
            "🎯 Кто тебя обосрал: пока никто."
            if lang == "ru"
            else "🎯 Хто тебе обісрав: поки ніхто."
        )
    ranked = sorted(counts.items(), key=lambda x: int(x[1]), reverse=True)[:limit]
    lines: list[str] = []
    for i, (uid, cnt) in enumerate(ranked, start=1):
        label = names.get(str(uid), f"id:{uid}")
        lines.append(
            f"{i}. {label} — {cnt} раз"
            if lang == "ru"
            else f"{i}. {label} — {cnt} разів"
        )
    header = "🎯 Кто тебя обосрал:" if lang == "ru" else "🎯 Хто тебе обісрав:"
    return header + "\n" + "\n".join(lines)


def _shit_given_top_block(lang: str, shit_given: dict, limit: int = 10) -> str:
    data = _normalize_shit_received(shit_given)
    counts = data.get("counts") or {}
    names = data.get("names") or {}
    header = "💩 Обосрал больше всего:" if lang == "ru" else "💩 Обісрав найбільше:"
    if not counts:
        none_line = "Никого" if lang == "ru" else "Нікого"
        return header + "\n" + none_line
    ranked = sorted(counts.items(), key=lambda x: int(x[1]), reverse=True)[:limit]
    lines: list[str] = []
    for i, (uid, cnt) in enumerate(ranked, start=1):
        label = names.get(str(uid), f"id:{uid}")
        lines.append(
            f"{i}. {label} — {cnt} раз"
            if lang == "ru"
            else f"{i}. {label} — {cnt} разів"
        )
    return header + "\n" + "\n".join(lines)


def _increment_shit_received(victim_profile: dict, attacker: User) -> int:
    data = _normalize_shit_received(victim_profile.get("shit_received"))
    uid = str(attacker.id)
    data["counts"][uid] = int(data["counts"].get(uid, 0)) + 1
    data["names"][uid] = _display_name(attacker)
    victim_profile["shit_received"] = data
    if len(data["counts"]) >= 5:
        _unlock_direct_achievement(victim_profile, "shit_by_5_unique")
    return int(data["counts"][uid])


def _increment_shit_given(attacker_profile: dict, victim: User) -> None:
    data = _normalize_shit_received(attacker_profile.get("shit_given"))
    uid = str(victim.id)
    data["counts"][uid] = int(data["counts"].get(uid, 0)) + 1
    data["names"][uid] = _display_name(victim)
    attacker_profile["shit_given"] = data


def _normalize_username_token(raw: str) -> str:
    """NFKC + лише латиниця/цифри/_ як у публічних Telegram username."""
    s = unicodedata.normalize("NFKC", raw).strip().lstrip("@")
    ascii_clean = "".join(c for c in s if c.isascii() and (c.isalnum() or c == "_"))
    return ascii_clean or s


async def _user_from_username(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[User]:
    """Публічний @username → User через get_chat."""
    u = _normalize_username_token(username)
    if not u:
        return None
    tried_names: list[str] = []
    for cand in (u, u.lower()):
        if cand and cand not in tried_names:
            tried_names.append(cand)
    for candidate in tried_names:
        try:
            chat = await context.bot.get_chat(f"@{candidate}")
            if _chat_represents_user(chat):
                return User(
                    id=chat.id,
                    is_bot=False,
                    first_name=chat.first_name or "",
                    last_name=chat.last_name,
                    username=chat.username,
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_chat @%s: %s", candidate, exc)
            continue
    return None


def ip_username_candidates(message, context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    """Усі ніки з тексту /ip для підказок помилки (без запитів до API)."""
    text = message.text or message.caption or ""
    tried: list[str] = []

    def _add(tok: str) -> None:
        n = _normalize_username_token(tok)
        if n and n not in tried:
            tried.append(n)

    for raw in context.args or []:
        _add(raw)
    for ent in message.entities or []:
        if _entity_is_mention(ent):
            chunk = text[ent.offset : ent.offset + ent.length].strip().lstrip("@")
            _add(chunk)
    raw_text = (text or "").strip()
    m = _IP_USERNAME_FROM_TEXT.match(raw_text)
    if not m:
        m = _IP_USERNAME_ANYWHERE.search(raw_text)
    if m:
        _add(m.group(1))
    return tried


async def _resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ціль для /ip тощо:
    1) Явний нік: /ip @user або /ip user (args і/або entity mention; Telegram інколи не дублює @ у args).
    2) У групі: підсвічений учасник (text_mention).
    3) Інакше — відповідь на повідомлення людини.
    """
    message = update.effective_message
    if not message:
        return None
    text = message.text or message.caption or ""

    tried = ip_username_candidates(message, context)

    for uname in tried:
        user_obj = await _user_from_username(context, uname)
        if user_obj:
            return user_obj

    if message.entities:
        for ent in message.entities:
            if _entity_is_text_mention(ent) and ent.user and not ent.user.is_bot:
                return ent.user

    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        if not u.is_bot:
            return u
    return None


def _inv_take(profile: dict, key: str, amount: int = 1) -> bool:
    inv = profile.get("inventory") or {}
    current = int(inv.get(key, 0))
    if current < amount:
        return False
    new_val = current - amount
    if new_val <= 0:
        inv.pop(key, None)
    else:
        inv[key] = new_val
    profile["inventory"] = inv
    return True


async def _fetch_member_user(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, uid: int
) -> Optional[User]:
    try:
        m = await context.bot.get_chat_member(chat_id, uid)
        if m.user and not m.user.is_bot:
            return m.user
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_chat_member %s %s: %s", chat_id, uid, exc)
    return None


async def _kakapair_candidate_ids(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for uid in context.chat_data.get("kakapair_recent_users") or []:
        if uid > 0 and uid not in seen:
            seen.add(uid)
            ordered.append(uid)
    if len(ordered) >= 2:
        return ordered
    try:
        for m in await context.bot.get_chat_administrators(chat_id):
            u = m.user
            if u and not u.is_bot and u.id not in seen:
                seen.add(u.id)
                ordered.append(u.id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("kakapair get_chat_administrators: %s", exc)
    return ordered


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    if chat.type == "private":
        return True
    member = await context.bot.get_chat_member(chat.id, user.id)
    return member.status in {ChatMember.ADMINISTRATOR, ChatMember.OWNER}


def _is_bot_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user or not user.username:
        return False
    expected = (context.bot_data.get("BOT_OWNER_USERNAME") or BOT_OWNER_USERNAME).strip().lstrip("@").lower()
    return bool(expected) and user.username.lower() == expected


async def _send_digest_reject(update: Update, context: ContextTypes.DEFAULT_TYPE, wait_min: int, lang: str) -> None:
    text = (
        f"Прошлая еда ещё переваривается — подожди ещё {wait_min} мин, желудок в турборежиме."
        if lang == "ru"
        else f"Попередня їжа ще перетравлюється — почекай ще {wait_min} хв, шлунок у турборежимі."
    )
    await update.effective_message.reply_text(text)
    if not await copy_random_gif_to_chat(context, update.effective_chat.id, max_try=15):
        logger.warning("digest reject: не удалось скопировать GIF из канала")


async def _process_poop(context: ContextTypes.DEFAULT_TYPE, profile: dict, forced: bool = False) -> None:
    stomach = profile["stomach"]
    if not stomach:
        return

    tags = [item["tag"] for item in stomach]
    power = _resolve_poop_power_from_stomach(stomach, forced=forced)

    profile["poop_count"] += 1
    profile["total_poop_power"] += power
    profile["best_poop_power"] = max(profile["best_poop_power"], power)
    new_achievements = _update_achievements(profile, power)
    profile["stomach"] = []
    profile["next_poop_ts"] = None
    _save_profile(profile)

    lang = profile["lang"]
    avg = profile["total_poop_power"] / max(1, profile["poop_count"])
    mention_label = "user"
    try:
        member = await context.bot.get_chat_member(profile["chat_id"], profile["user_id"])
        mention_label = _display_name(member.user)
    except Exception:  # noqa: BLE001
        mention_label = str(profile["user_id"])
    mention = f"<a href='tg://user?id={profile['user_id']}'>{html.escape(mention_label)}</a>"
    text = (
        f"💥 {mention}, запуск какания: {power:.1f}%\n"
        f"{_result_line(lang, power)}\n"
        f"{_combo_text(lang, tags)}\n"
        f"{_random_poop_meme_line(lang)}\n\n"
        f"Всего какал: {profile['poop_count']} раз\n"
        f"Лучший результат: {profile['best_poop_power']:.1f}%\n"
        f"Общий уровень: {_rank(lang, avg)}\n"
        f"{_weight_line(lang, int(profile.get('eat_count', 0)))}"
        if lang == "ru"
        else (
            f"💥 {mention}, запуск какання: {power:.1f}%\n"
            f"{_result_line(lang, power)}\n"
            f"{_combo_text(lang, tags)}\n"
            f"{_random_poop_meme_line(lang)}\n\n"
            f"Всього какав: {profile['poop_count']} разів\n"
            f"Найкращий результат: {profile['best_poop_power']:.1f}%\n"
            f"Загальний рівень: {_rank(lang, avg)}\n"
            f"{_weight_line(lang, int(profile.get('eat_count', 0)))}"
        )
    )
    if new_achievements:
        text += (
            "\n\n🏆 Новые достижения:\n" + _achievement_labels(lang, new_achievements)
            if lang == "ru"
            else "\n\n🏆 Нові досягнення:\n" + _achievement_labels(lang, new_achievements)
        )
    chat_id = profile["chat_id"]
    try:
        await context.bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send poop result to user %s: %s", profile["user_id"], exc)
        return
    try:
        if not await copy_random_gif_to_chat(context, chat_id, max_try=20):
            logger.warning(
                "Какание: анимация из канала не скопировалась (user %s, chat %s). Проверь GIF_POST_IDS и права бота.",
                profile["user_id"],
                chat_id,
            )
    except Exception as gif_exc:  # noqa: BLE001
        logger.warning("Какание: ошибка копирования GIF: %s", gif_exc)


async def pokushat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return

    lang = context.chat_data.get("lang", detect_lang(message.text or ""))
    now = time.time()
    profile = _load_profile(user.id, chat.id, lang)
    profile["chat_id"] = chat.id
    profile["lang"] = lang

    elapsed = now - float(profile["last_eat_ts"])
    if elapsed < EAT_COOLDOWN_SEC:
        wait_min = int((EAT_COOLDOWN_SEC - elapsed + 59) // 60)
        await _send_digest_reject(update, context, wait_min, lang)
        return

    inv_food = _take_inventory_food(profile)
    if inv_food:
        chosen_name = inv_food["uk"] if lang == "uk" else inv_food["ru"]
        picked_ru = inv_food["ru"]
        picked_uk = inv_food["uk"]
        picked_bonus = int(inv_food["bonus"])
        picked_tag = inv_food["tag"]
        from_inventory = True
    else:
        foods = _load_foods_from_file() or FOODS
        picked = random.choice(foods)
        chosen_name = picked.uk if lang == "uk" else picked.ru
        picked_ru = picked.ru
        picked_uk = picked.uk
        picked_bonus = picked.bonus
        picked_tag = picked.tag
        from_inventory = False
    stomach = list(profile["stomach"])
    overflow = len(stomach) >= 3
    if overflow:
        stomach.pop(0)
    stomach.append({"ru": picked_ru, "uk": picked_uk, "bonus": picked_bonus, "tag": picked_tag})
    profile["stomach"] = stomach
    profile["eat_count"] = int(profile.get("eat_count", 0)) + 1
    profile["last_eat_ts"] = now
    if picked_tag == "inedible" or picked_bonus >= 60:
        _unlock_direct_achievement(profile, "rare_food_once")

    if profile.get("next_poop_ts") is None:
        profile["next_poop_ts"] = now + FIRST_POOP_DELAY_SEC

    _save_profile(profile)

    pre = (
        f"Ты только что слопал {chosen_name} 🔥 Теперь в тебе булькает..."
        if lang == "ru"
        else f"Ти щойно з'їв {chosen_name} 🔥 Тепер у тобі булькає..."
    )
    if from_inventory:
        pre += (
            "\n📦 Еда взята из инвентаря."
            if lang == "ru"
            else "\n📦 Їжу взято з інвентаря."
        )
    if overflow:
        pre += (
            "\n⚠️ Желудок переполнен: старое содержимое вытолкнуло наружу."
            if lang == "ru"
            else "\n⚠️ Шлунок переповнений: старий вміст витиснуло назовні."
        )
    await message.reply_text(pre)

    # Random drop system: "charcoal for stomach"
    if random.random() < 0.09:
        _inv_add(profile, "stomach_charcoal", 1)
        _save_profile(profile)
        await message.reply_text(
            "🎁 Лут: выпал «уголь для желудка»! Используй /pilsl чтобы обнулить кулдаун еды."
            if lang == "ru"
            else "🎁 Лут: випало «вугілля для шлунка»! Використай /pilsl щоб обнулити кулдаун їжі."
        )

    acc = _stomach_accumulated_power(stomach)
    delay_msg = (
        f"Ты покушал. Накоплено ~{acc:.1f}% к силе какания. "
        f"В следующий раз можно поесть через {EAT_COOLDOWN_MIN} минут. "
        f"Покакать получится через {POOP_URGE_DELAY_MIN} минут от первого приёма в этом цикле "
        f"(даже если ты поел только один раз — таймер всё равно дойдёт)."
        if lang == "ru"
        else (
            f"Ти поїв. Накопичено ~{acc:.1f}% до сили какання. "
            f"Наступного разу можна поїсти через {EAT_COOLDOWN_MIN} хвилин. "
            f"Покакати вийде через {POOP_URGE_DELAY_MIN} хвилин від першого прийому в цьому циклі "
            f"(навіть якщо ти їв лише раз — таймер усе одно спрацює)."
        )
    )
    await message.reply_text(delay_msg)

    try:
        if not await copy_random_gif_to_chat(context, chat.id, max_try=15):
            logger.warning(
                "Приём пищи: не удалось скопировать GIF из канала (chat %s). Проверь GIF_POST_IDS.",
                chat.id,
            )
    except Exception as gif_exc:  # noqa: BLE001
        logger.warning("Приём пищи: ошибка копирования GIF: %s", gif_exc)


def _fit_telegram_photo_caption(prefix: str, stats_body: str, max_len: int = 1024) -> str:
    """Подпись к фото: prefix (шапка + досье) не трогаем; статистику укорачиваем снизу."""
    if len(prefix) > max_len:
        return prefix[: max_len - 1] + "…"
    combined = prefix + stats_body
    if len(combined) <= max_len:
        return combined
    lines = stats_body.split("\n")
    dropped = 0
    while lines:
        combined = prefix + "\n".join(lines)
        if len(combined) <= max_len:
            out = combined
            if dropped > 0 and len(out) + 2 <= max_len:
                out += "\n…"
            elif dropped > 0:
                out = out[: max_len - 1] + "…"
            return out[:max_len]
        lines.pop()
        dropped += 1
    return prefix[:max_len]


def _mystat_stats_body(
    lang: str,
    profile: dict,
    avg: float,
    achievements_line: str,
    stomach: list,
    *,
    shit_limit: int = 10,
) -> str:
    if lang == "ru":
        return (
            f"💩 Какал: {profile['poop_count']} раз\n"
            f"⭐ Лучший результат: {profile['best_poop_power']:.1f}%\n"
            f"📈 Средняя сила: {avg:.1f}%\n"
            f"🏅 Ранг: {_rank(lang, avg)}\n"
            f"{_weight_line(lang, int(profile.get('eat_count', 0)))}\n"
            f"{achievements_line}\n"
            f"{_inventory_block(lang, profile)}\n"
            f"{_shit_top_block(lang, profile.get('shit_received'), limit=shit_limit)}\n"
            f"{_shit_given_top_block(lang, profile.get('shit_given'), limit=shit_limit)}\n"
            f"{_stomach_status_line(lang, stomach)}\n"
            f"{_stomach_poop_range_line(lang, stomach)}"
        )
    return (
        f"💩 Какав: {profile['poop_count']} разів\n"
        f"⭐ Найкращий результат: {profile['best_poop_power']:.1f}%\n"
        f"📈 Середня сила: {avg:.1f}%\n"
        f"🏅 Ранг: {_rank(lang, avg)}\n"
        f"{_weight_line(lang, int(profile.get('eat_count', 0)))}\n"
        f"{achievements_line}\n"
        f"{_inventory_block(lang, profile)}\n"
        f"{_shit_top_block(lang, profile.get('shit_received'), limit=shit_limit)}\n"
        f"{_shit_given_top_block(lang, profile.get('shit_given'), limit=shit_limit)}\n"
        f"{_stomach_status_line(lang, stomach)}\n"
        f"{_stomach_poop_range_line(lang, stomach)}"
    )


async def mystat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Профиль / статистика: /mystat, /my_poop или отдельным сообщением «я»."""
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    lang = context.chat_data.get("lang", "uk")
    profile = _load_profile(user.id, chat.id, lang)
    avg = profile["total_poop_power"] / max(1, profile["poop_count"])
    unlocked = list((profile.get("achievements") or {}).get("unlocked", []))
    stomach = profile["stomach"]
    requester = _display_name(user)
    force_oc = _is_bot_owner(update, context)
    dossier_sec = _ip_dossier_profile_section(
        lang, profile, requester, force_owner_classified=force_oc
    )
    inv = profile.get("inventory") or {}
    raw_ip = inv.get("ip_dossier") if isinstance(inv.get("ip_dossier"), dict) else None
    dossier_photo: dict | None = None
    if force_oc:
        dossier_photo = owner_classified_dossier_v2(lang)
    elif raw_ip and is_v2_ip_dossier(raw_ip):
        dossier_photo = raw_ip

    head_line = f"📊 Статистика {requester}:"
    achievements_line = (
        ("🎖️ Достижения: пока нет" if lang == "ru" else "🎖️ Досягнення: поки немає")
        if not unlocked
        else (
            ("🎖️ Достижения:\n" if lang == "ru" else "🎖️ Досягнення:\n")
            + _achievement_labels(lang, sorted(unlocked))
        )
    )
    stats_body = _mystat_stats_body(lang, profile, avg, achievements_line, stomach, shit_limit=10)

    url = ""
    if dossier_photo:
        url = str(dossier_photo.get("photo_url") or "").strip()

    if url:
        dt = format_ip_dossier_caption(requester, dossier_photo, lang)
        prefix = f"{head_line}\n\n{dt}\n\n"
        caption = _fit_telegram_photo_caption(prefix, stats_body)
        try:
            await message.reply_photo(photo=url, caption=caption)
        except TelegramError:
            fb = f"{head_line}\n\n{dt}\n\n{stats_body}"
            await message.reply_text(fb[:4096])
        if (message.text or "").strip() == "я":
            raise ApplicationHandlerStop
        return

    if dossier_sec:
        text = f"{head_line}\n\n{dossier_sec}\n\n{stats_body}"
    else:
        text = f"{head_line}\n\n{stats_body}"
    await message.reply_text(text)
    if (message.text or "").strip() == "я":
        raise ApplicationHandlerStop


async def datedu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    lang = context.chat_data.get("lang", "uk")
    if not _is_bot_owner(update, context):
        await message.reply_text(
            "Только владелец бота (@rofl3121) может вызвать эту команду."
            if lang == "ru"
            else "Лише власник бота (@rofl3121) може викликати цю команду."
        )
        return

    target = await _resolve_target_user(update, context)
    if not target or target.id == user.id:
        await message.reply_text(
            "Укажи получателя: ответом или /datedu @username"
            if lang == "ru"
            else "Вкажи отримувача: відповіддю або /datedu @username"
        )
        return

    foods = _load_foods_from_file() or FOODS
    picked = random.choice(foods)
    target_profile = _load_profile(target.id, chat.id, lang)
    target_profile["chat_id"] = chat.id
    target_profile["lang"] = lang
    _grant_food_to_inventory(target_profile, picked)
    _save_profile(target_profile)

    target_name = _display_name(target)
    food_name = picked.uk if lang == "uk" else picked.ru
    await message.reply_text(
        f"🎁 Для {target_name} в инвентарь добавила еду: {food_name}. Съесть можно через /eat."
        if lang == "ru"
        else f"🎁 Для {target_name} додала в інвентар їжу: {food_name}. З'їсти можна через /eat."
    )


async def obosrat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    lang = context.chat_data.get("lang", "uk")

    target = await _resolve_target_user(update, context)
    if not target or target.id == user.id:
        await message.reply_text(
            "Ответь на сообщение или укажи ник: /obosrat @username"
            if lang == "ru"
            else "Відповідай на повідомлення або вкажи нік: /obosrat @username"
        )
        return

    attacker_profile = _load_profile(user.id, chat.id, lang)
    attacker_profile["chat_id"] = chat.id
    attacker_profile["lang"] = lang

    eat_count = int(attacker_profile.get("eat_count", 0))
    last_o = int(attacker_profile.get("last_obosrat_at_eat_count", -1))

    if eat_count < 1:
        await message.reply_text(
            "Сначала прими пищу: /pokushat. Без первого приёма «обосрать» нельзя."
            if lang == "ru"
            else "Спочатку прийми їжу: /pokushat. Без першого прийому «обісрати» не можна."
        )
        return
    if not (eat_count > last_o):
        await message.reply_text(
            "Ты уже потратил шанс. Съешь ещё раз (/pokushat) — после следующего приёма снова можно."
            if lang == "ru"
            else "Ти вже витратив шанс. З'їж ще раз (/pokushat) — після наступного прийому знову можна."
        )
        return

    victim_profile = _load_profile(target.id, chat.id, lang)
    victim_profile["chat_id"] = chat.id
    victim_profile["lang"] = lang

    total_vs_victim = _increment_shit_received(victim_profile, user)
    _increment_shit_given(attacker_profile, target)
    attacker_profile["last_obosrat_at_eat_count"] = eat_count

    _save_profile(victim_profile)
    _save_profile(attacker_profile)

    att_label = _display_name(user)
    vic_label = _display_name(target)
    story_line = random.choice(OBOSRAT_LINES_UK if lang == "uk" else OBOSRAT_LINES_RU).format(
        attacker=att_label,
        count=total_vs_victim,
    )
    await message.reply_text(
        (
            f"{story_line}\n"
            f"У {vic_label} в стате: «{att_label} обосрал вас {total_vs_victim} раз»."
        )
        if lang == "ru"
        else f"{story_line}\nУ {vic_label} в статі: «{att_label} обісрав вас {total_vs_victim} разів»."
    )


async def kakapair_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Випадкова пара учасників: хто на кого — зараховується в shit_given / shit_received (без їжі)."""
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not chat:
        return
    lang = context.chat_data.get("lang", detect_lang(message.text or ""))
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(
            "Команда /kakapair только для групп."
            if lang == "ru"
            else "Команда /kakapair лише для груп."
        )
        return

    if user and not user.is_bot:
        lst = context.chat_data.setdefault("kakapair_recent_users", [])
        try:
            lst.remove(user.id)
        except ValueError:
            pass
        lst.append(user.id)

    now = time.time()
    if now - float(context.chat_data.get("kakapair_last_ts", 0.0)) < KAKAPAIR_COOLDOWN_SEC:
        wait = int(KAKAPAIR_COOLDOWN_SEC - (now - float(context.chat_data.get("kakapair_last_ts", 0.0))) + 0.99)
        await message.reply_text(
            f"Пару секунд терпения — /kakapair можно снова через ~{wait} с."
            if lang == "ru"
            else f"Зачекай — /kakapair знову через ~{wait} с."
        )
        return

    candidates = await _kakapair_candidate_ids(context, chat.id)
    if len(candidates) < 2:
        await message.reply_text(
            "Мало людей для случайной пары: пусть в чате напишут хотя бы двое (или добавьте бота с правами видеть участников)."
            if lang == "ru"
            else "Мало людей для випадкової пари: нехай у чаті напишуть хоча б двоє (або перевір права бота)."
        )
        return

    users_pair: Optional[tuple[User, User]] = None
    if len(candidates) == 2:
        ua = await _fetch_member_user(context, chat.id, candidates[0])
        ub = await _fetch_member_user(context, chat.id, candidates[1])
        if ua and ub:
            users_pair = (ua, ub)
    else:
        for _ in range(28):
            uid_a, uid_b = random.sample(candidates, 2)
            ua = await _fetch_member_user(context, chat.id, uid_a)
            ub = await _fetch_member_user(context, chat.id, uid_b)
            if ua and ub:
                users_pair = (ua, ub)
                break

    if not users_pair:
        await message.reply_text(
            "Мне не удалось получить пару через Telegram API. Попробуй позже."
            if lang == "ru"
            else "Мені не вдалося отримати пару через Telegram API. Спробуй пізніше."
        )
        return

    if random.random() < 0.5:
        attacker, victim = users_pair[0], users_pair[1]
    else:
        attacker, victim = users_pair[1], users_pair[0]

    attacker_profile = _load_profile(attacker.id, chat.id, lang)
    attacker_profile["chat_id"] = chat.id
    attacker_profile["lang"] = lang
    victim_profile = _load_profile(victim.id, chat.id, lang)
    victim_profile["chat_id"] = chat.id
    victim_profile["lang"] = lang

    total_vs_victim = _increment_shit_received(victim_profile, attacker)
    _increment_shit_given(attacker_profile, victim)

    _save_profile(victim_profile)
    _save_profile(attacker_profile)

    context.chat_data["kakapair_last_ts"] = now

    att_label = _display_name(attacker)
    vic_label = _display_name(victim)
    story_line = random.choice(OBOSRAT_LINES_UK if lang == "uk" else OBOSRAT_LINES_RU).format(
        attacker=att_label,
        count=total_vs_victim,
    )
    header = (
        f"🎲 Случайная пара: {att_label} → {vic_label}\n{story_line}\n"
        f"У {vic_label} в стате: «{att_label} обосрал вас {total_vs_victim} раз»."
        if lang == "ru"
        else f"🎲 Випадкова пара: {att_label} → {vic_label}\n{story_line}\n"
        f"У {vic_label} в статі: «{att_label} обісрав вас {total_vs_victim} разів»."
    )
    await message.reply_text(header)


async def pilsl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    lang = context.chat_data.get("lang", "uk")
    profile = _load_profile(user.id, chat.id, lang)

    if not _inv_take(profile, "stomach_charcoal", 1):
        await message.reply_text(
            "У тебя нет «угля для желудка». Сначала выбей его через /pokushat."
            if lang == "ru"
            else "У тебе нема «вугілля для шлунка». Спочатку вибий його через /pokushat."
        )
        return

    profile["last_eat_ts"] = 0.0
    _unlock_direct_achievement(profile, "pill_used_once")
    _save_profile(profile)
    left = int((profile.get("inventory") or {}).get("stomach_charcoal", 0))
    await message.reply_text(
        f"💊 /pilsl сработала: кулдаун еды сбросила, снова можно /pokushat. Угля осталось: {left}"
        if lang == "ru"
        else f"💊 /pilsl спрацювала: кулдаун їжі скинула, знову можна /pokushat. Вугілля залишилось: {left}"
    )


async def pokakat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    lang = context.chat_data.get("lang", "uk")
    if not _is_bot_owner(update, context):
        await message.reply_text(
            "Только владелец бота (@rofl3121) может вызвать эту команду."
            if lang == "ru"
            else "Лише власник бота (@rofl3121) може викликати цю команду."
        )
        return

    target = await _resolve_target_user(update, context)
    if not target:
        await message.reply_text(
            "Кого заставить покакать? Ответь на сообщение или: /pokakat @username"
            if lang == "ru"
            else "Кого змусити покакати? Відповідь на повідомлення або: /pokakat @username"
        )
        return

    profile = _load_profile(target.id, chat.id, lang)
    profile["chat_id"] = chat.id
    profile["lang"] = lang
    if not profile.get("stomach"):
        await message.reply_text(
            "Нечем какать: желудок пуст."
            if lang == "ru"
            else "Нема чим какати: шлунок порожній."
        )
        return

    await _process_poop(context, profile, forced=True)


async def force_poop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    lang = context.chat_data.get("lang", "uk")
    if not _is_bot_owner(update, context):
        await message.reply_text(
            "Только владелец бота (@rofl3121) может вызвать эту команду."
            if lang == "ru"
            else "Лише власник бота (@rofl3121) може викликати цю команду."
        )
        return

    target_user = message.reply_to_message.from_user if message.reply_to_message else update.effective_user
    if not target_user:
        return
    profile = _load_profile(target_user.id, chat.id, lang)
    if not profile["stomach"]:
        await message.reply_text(
            "Желудок пуст. Нечего форсить." if lang == "ru" else "Шлунок порожній. Нема чого форсити."
        )
        return
    await _process_poop(context, profile, forced=True)


async def poop_scheduler_loop(app: Application) -> None:
    await asyncio.sleep(5)
    while True:
        try:
            now = time.time()
            with _conn() as conn:
                rows = conn.execute(
                    """
                    SELECT user_id, chat_id, lang, last_eat_ts, stomach_json, eat_count, poop_count,
                           inventory_json, total_poop_power, best_poop_power, achievements_json,
                           shit_received_json, shit_given_json, last_obosrat_at_eat_count, next_poop_ts
                    FROM poop_profiles
                    WHERE next_poop_ts IS NOT NULL AND next_poop_ts <= ?
                    """,
                    (now,),
                ).fetchall()
            for row in rows:
                profile = {
                    "user_id": row[0],
                    "chat_id": row[1],
                    "lang": row[2],
                    "last_eat_ts": row[3],
                    "stomach": json.loads(row[4]),
                    "eat_count": row[5],
                    "poop_count": row[6],
                    "inventory": json.loads(row[7] or "{}"),
                    "total_poop_power": row[8],
                    "best_poop_power": row[9],
                    "achievements": json.loads(row[10] or "{}"),
                    "shit_received": _normalize_shit_received(json.loads(row[11] or "{}")),
                    "shit_given": _normalize_shit_received(json.loads(row[12] or "{}")),
                    "last_obosrat_at_eat_count": row[13],
                    "next_poop_ts": row[14],
                }
                await _process_poop(app, profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("poop scheduler error: %s", exc)
        await asyncio.sleep(SCHEDULER_TICK_SEC)


async def start_poop_background(app: Application) -> None:
    init_db()
    app.create_task(poop_scheduler_loop(app))


def register_poop_handlers(app: Application) -> None:
    app.add_handler(CommandHandler(["pokushat", "eat"], pokushat_command))
    app.add_handler(CommandHandler(["mystat", "my_poop"], mystat_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r"^я$"),
            mystat_command,
        ),
        group=1,
    )
    app.add_handler(CommandHandler("datedu", datedu_command))
    app.add_handler(CommandHandler("obosrat", obosrat_command))
    app.add_handler(CommandHandler("kakapair", kakapair_command))
    app.add_handler(CommandHandler("pilsl", pilsl_command))
    app.add_handler(CommandHandler("pokakat", pokakat_command))
    app.add_handler(CommandHandler("force_poop", force_poop_command))
