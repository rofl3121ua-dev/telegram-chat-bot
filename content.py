import logging
import os
from datetime import datetime
from random import choice
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

FALLBACK_PICTURES: list[str] = [
    "https://images.unsplash.com/photo-1518717758536-85ae29035b6d",
    "https://images.unsplash.com/photo-1495360010541-f48722b34f7d",
    "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba",
    "https://images.unsplash.com/photo-1474511320723-9a56873867b5",
    "https://images.unsplash.com/photo-1535930749574-1399327ce78f",
    "https://images.unsplash.com/photo-1525253086316-d0c936c814f8",
    "https://images.unsplash.com/photo-1545239351-1141bd82e8a6",
    "https://images.unsplash.com/photo-1533743983669-94fa5c4338ec",
    "https://images.unsplash.com/photo-1529778873920-4da4926a72c2",
    "https://images.unsplash.com/photo-1543852786-1cf6624b9987",
    "https://images.unsplash.com/photo-1517849845537-4d257902454a",
    "https://images.unsplash.com/photo-1574158622682-e40e69881006",
]

PIZDY_LINES_RU: list[str] = [
    "⚔️ {target} попал под рейд мем-полиции. Получил словесный лещ и гиф-шторм.",
    "💥 {target}, сегодня ты официальный чемпион по провокациям. Наказание: 3 тонны кринжа.",
    "🧨 {target}, тебе выписан эпичный разнос с фанфарами и драматичной гифкой.",
]

PIZDY_LINES_UK: list[str] = [
    "⚔️ {target} потрапив під рейд мем-поліції. Отримав словесний лящ і гіф-шторм.",
    "💥 {target}, сьогодні ти чемпіон провокацій. Покарання: 3 тонни крінжу.",
    "🧨 {target}, тобі виписано епічний рознос із фанфарами та драматичною гіфкою.",
]

RANDOM_REPLIES_RU: list[str] = [
    "Этот чат сегодня на максимальном вайбе.",
    "Накал обсуждения: 9000.",
    "Кто-то явно заебывал всех, но это весело.",
    "Спокойно, без паники, с мемами.",
    "Тихо, не спеша, без суеты — и с орущими стикерами.",
    "Tung tung tung sahur: чат снова не спит.",
    "Балерина капучино одобряет этот поток мыслей.",
    "Режим «прочитал и переслал в мемы» активирован.",
    "Сюжет плотнее, чем у сериалов на 8 сезонов.",
    "Сейчас бы протокол дискуссии, а не это вот все.",
    "Чат жив, пока в нем спорят про еду и проценты.",
    "Это сообщение пахнет вирусным тиктоком.",
    "Факт дня: кто пишет первым, тот и прав (нет).",
    "Модераторы на паузе, мемы на ускорении.",
    "Если это не контент, то что тогда контент?",
    "План был простой. Как всегда, не сработал.",
    "Вижу сообщение — слышу драматичную музыку.",
    "Официально: чат перешел в фазу легенд.",
    "Это не флуд, это сериал в реальном времени.",
    "Где-то сейчас аплодирует один SMM-щик.",
    "Сначала было слово, потом 200 уведомлений.",
    "Ставлю лайк этой энергетике.",
    "Всем сохранять спокойствие и отправлять мемы.",
    "Плотность шуток выше нормы, продолжаем.",
    "Тред настолько горячий, что нужен огнетушитель.",
    "Даже алгоритмы немного в шоке.",
    "Этот диалог войдет в учебники по хаосу.",
    "Нормально общались ровно 3 секунды.",
    "Здесь каждая реплика как новый сезон.",
    "Все по классике: вопрос, спор, мем, финал.",
    "Чат официально в режиме «еще пять минут».",
    "Тут либо гениально, либо очень смело.",
    "Кажется, это уже лор вашего чата.",
    "Энергия треда: от 0 до апокалипсиса.",
    "Кто-то должен это экранизировать.",
    "С каждой минутой все кинематографичнее.",
    "База, кринж и постирония в одном флаконе.",
    "Так, это уже похоже на стендап.",
    "Эту переписку надо читать с озвучкой.",
    "Ладно, это действительно смешно.",
]

RANDOM_REPLIES_UK: list[str] = [
    "Цей чат сьогодні на максимальному вайбі.",
    "Накал обговорення: 9000.",
    "Хтось явно діставав усіх, але це весело.",
    "Спокійно, без паніки, з мемами.",
    "Тихо, не поспішаючи, без метушні — і з гучними стікерами.",
    "Tung tung tung sahur: чат знову не спить.",
    "Балерина капучино схвалює цей потік думок.",
    "Режим «прочитав і кинув у меми» активовано.",
    "Сюжет щільніший, ніж у серіалу на 8 сезонів.",
    "Зараз би протокол дискусії, а не оце все.",
    "Чат живий, поки в ньому сперечаються про їжу і відсотки.",
    "Це повідомлення пахне вірусним тіктоком.",
    "Факт дня: хто пише першим, той і правий (ні).",
    "Модератори на паузі, меми на прискоренні.",
    "Якщо це не контент, то що тоді контент?",
    "План був простий. Як завжди, не спрацював.",
    "Бачу повідомлення — чую драматичну музику.",
    "Офіційно: чат перейшов у фазу легенд.",
    "Це не флуд, це серіал у реальному часі.",
    "Десь зараз аплодує один SMM-ник.",
    "Спочатку було слово, потім 200 сповіщень.",
    "Ставлю лайк цій енергетиці.",
    "Усім зберігати спокій і надсилати меми.",
    "Щільність жартів вища за норму, продовжуємо.",
    "Тред настільки гарячий, що потрібен вогнегасник.",
    "Навіть алгоритми трохи в шоці.",
    "Цей діалог увійде в підручники з хаосу.",
    "Нормально спілкувалися рівно 3 секунди.",
    "Тут кожна репліка як новий сезон.",
    "Усе за класикою: питання, суперечка, мем, фінал.",
    "Чат офіційно в режимі «ще п'ять хвилин».",
    "Тут або геніально, або дуже сміливо.",
    "Схоже, це вже лор вашого чату.",
    "Енергія треду: від 0 до апокаліпсису.",
    "Хтось має це екранізувати.",
    "Щохвилини все кінематографічніше.",
    "База, крінж і постіронія в одному флаконі.",
    "Так, це вже схоже на стендап.",
    "Цю переписку треба читати з озвучкою.",
    "Гаразд, це справді смішно.",
]

FAKE_MUTE_LINES_RU: list[str] = [
    "⚠️ {user}, слишком шумно в чате. ШУТОЧНЫЙ мут на 24 часа (без реальных санкций).",
    "🚨 {user}, чат ловит перегруз. Назначен декоративный мут на 24 часа.",
    "🛑 {user}, у тебя сегодня турбо-режим. Выдан символический мут на сутки.",
    "📢 {user}, громкость 300%. Шутливый мут на 24 часа для баланса вселенной.",
    "🧯 {user}, дискуссия загорелась. Включаю фейк-мут на 24 часа.",
    "🫡 {user}, мем-полиция попросила паузу. ШУТОЧНЫЙ мут: 24 часа.",
    "🎭 {user}, это был слишком мощный перформанс. Фейк-мут на сутки.",
    "⏸️ {user}, берём драматическую паузу. Символический мут: 24 часа.",
    "🔇 {user}, чат устал аплодировать. Назначен мягкий фейк-мут на 24 часа.",
    "📜 {user}, по кодексу мемов: сутки шуточного мута.",
]

FAKE_MUTE_LINES_UK: list[str] = [
    "⚠️ {user}, занадто гучно в чаті. ЖАРТІВЛИВИЙ мут на 24 години (без реальних санкцій).",
    "🚨 {user}, чат ловить перевантаження. Призначено декоративний мут на 24 години.",
    "🛑 {user}, у тебе сьогодні турбо-режим. Видано символічний мут на добу.",
    "📢 {user}, гучність 300%. Жартівливий мут на 24 години для балансу всесвіту.",
    "🧯 {user}, дискусія загорілась. Вмикаю фейк-мут на 24 години.",
    "🫡 {user}, мем-поліція попросила паузу. ЖАРТІВЛИВИЙ мут: 24 години.",
    "🎭 {user}, це був надто потужний перформанс. Фейк-мут на добу.",
    "⏸️ {user}, беремо драматичну паузу. Символічний мут: 24 години.",
    "🔇 {user}, чат втомився аплодувати. Призначено м'який фейк-мут на 24 години.",
    "📜 {user}, за кодексом мемів: доба жартівливого муту.",
]

EDGE_REPLIES_RU: list[str] = [
    "Чёрный юмор включила — но без перехода границ.",
    "Эджи-режим: шучу острее, к людям мягче.",
]

EDGE_REPLIES_UK: list[str] = [
    "Чорний гумор увімкнула — але без переходу меж.",
    "Еджі-режим: жартую гостріше, до людей м'якше.",
]

ROAST_REPLIES_RU: list[str] = [
    "Сильный заход. Жаль, смысл опоздал на другой поезд.",
    "Ты как Wi‑Fi в метро: шума много, пользы мало.",
    "Уверенность 10/10, аргументы где-то в отпуске.",
    "Сообщение громкое, как реклама, и такое же информативное.",
    "Это было смело. Теперь попробуй еще и умно.",
    "Твоя логика сегодня на энергосбережении.",
    "Не спорю, красиво. Но с фактами было бы лучше.",
    "План отличный, реализация — как всегда на авось.",
    "Чат услышал тебя. Теперь бы еще понять зачем.",
    "Минутка самоуверенности успешно завершена.",
]

ROAST_REPLIES_UK: list[str] = [
    "Потужний захід. Шкода, сенс запізнився на інший потяг.",
    "Ти як Wi‑Fi у метро: шуму багато, користі мало.",
    "Впевненість 10/10, аргументи десь у відпустці.",
    "Повідомлення гучне, як реклама, і таке ж інформативне.",
    "Це було сміливо. Тепер спробуй ще й розумно.",
    "Твоя логіка сьогодні на енергозбереженні.",
    "Не сперечаюся, красиво. Але з фактами було б краще.",
    "План чудовий, реалізація — як завжди на авось.",
    "Чат почув тебе. Тепер би ще зрозуміти навіщо.",
    "Хвилинка самовпевненості успішно завершена.",
]

_BASE_DIR = Path(__file__).resolve().parent
CUSTOM_RANDOM_RU_FILE = _BASE_DIR / "custom_random_replies_ru.txt"
CUSTOM_RANDOM_UK_FILE = _BASE_DIR / "custom_random_replies_uk.txt"

# Один раз за процесс: без повторних WARNING у циклах (poop scheduler тощо).
_tz_initialized = False
_tz_cached: Optional[object] = None


def _bot_tz():
    global _tz_initialized, _tz_cached
    if _tz_initialized:
        return _tz_cached  # type: ignore[return-value]
    _tz_initialized = True
    name = (os.getenv("BOT_TIMEZONE") or "Europe/Kyiv").strip()
    if not name or ZoneInfo is None:
        _tz_cached = None
        return None
    try:
        _tz_cached = ZoneInfo(name)
        return _tz_cached
    except Exception:
        # На частині Windows немає tzdata — локальний час сервера ок для phrase_time_level.
        logger.debug("BOT_TIMEZONE=%r недоступен, берём локальное время сервера", name)
        _tz_cached = None
        return None


def _current_hour_local() -> int:
    tz = _bot_tz()
    if tz is not None:
        return datetime.now(tz).hour
    return datetime.now().hour


def phrase_time_level() -> int:
    """
    Уровни фраз по времени суток (локальное время BOT_TIMEZONE):
      1 — с 06:00 до 12:00
      2 — с 12:00 до 18:00
      3 — с 18:00 до 06:00
    """
    h = _current_hour_local()
    if 6 <= h < 12:
        return 1
    if 12 <= h < 18:
        return 2
    return 3


def _read_phrases(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def get_random_reply_pool(lang: str) -> list[str]:
    """
    Випадкові короткі відповіді в чаті (messages.on_regular_message).
    Спочатку шукаємо custom_random_replies_{uk|ru}_l{1|2|3}.txt за поточним рівнем часу.
    Якщо порожньо — загальний custom_random_replies_{uk|ru}.txt.
    Якщо й він порожній — вбудовані RANDOM_REPLIES_*.
    """
    code = "uk" if lang == "uk" else "ru"
    level = phrase_time_level()
    path_level = _BASE_DIR / f"custom_random_replies_{code}_l{level}.txt"
    loaded = _read_phrases(path_level)
    if loaded:
        return loaded
    path_flat = CUSTOM_RANDOM_UK_FILE if lang == "uk" else CUSTOM_RANDOM_RU_FILE
    loaded = _read_phrases(path_flat)
    if loaded:
        return loaded
    return RANDOM_REPLIES_UK if lang == "uk" else RANDOM_REPLIES_RU


def pick_picture() -> str:
    return choice(FALLBACK_PICTURES)


async def copy_random_gif_to_chat(context, chat_id: int, *, max_try: Optional[int] = None) -> bool:
    """Случайный пост из GIF_SOURCE_CHANNEL → в указанный чат (без ссылок из интернета)."""
    channel = context.bot_data.get("GIF_SOURCE_CHANNEL", "").strip()
    message_ids = context.bot_data.get("GIF_POST_IDS", [])
    if not channel or not message_ids:
        return False
    probe_attempts = int(context.bot_data.get("MEDIA_PROBE_ATTEMPTS", 1))
    if max_try is not None:
        max_attempts = min(max(1, max_try), len(message_ids))
    else:
        max_attempts = min(max(1, probe_attempts), len(message_ids))
    for _ in range(max_attempts):
        candidate = choice(message_ids)
        try:
            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=channel,
                message_id=candidate,
                caption="",
            )
            return True
        except Exception:
            continue
    return False


async def _copy_media_only(update, context, channel: str, message_ids: list[int], media_kind: str) -> bool:
    """
    Copy only media posts from a source channel.
    media_kind: "picture" or "gif"
    """
    message = update.effective_message
    if not message or not channel or not message_ids:
        return False

    # Fast mode: no media-type probing loops, just copy a random post.
    # This avoids flood limits and keeps the bot responsive while testing.
    probe_attempts = int(context.bot_data.get("MEDIA_PROBE_ATTEMPTS", 1))
    max_attempts = min(max(1, probe_attempts), len(message_ids))
    for _ in range(max_attempts):
        candidate = choice(message_ids)
        try:
            await context.bot.copy_message(
                chat_id=message.chat_id,
                from_chat_id=channel,
                message_id=candidate,
                caption="",
            )
            return True
        except Exception:
            continue
    return False


def _forum_thread_kwargs(message) -> dict:
    """Топик форума: пересылка и отправка должны попадать в ту же ветку."""
    mid = getattr(message, "message_thread_id", None)
    if getattr(message, "is_topic_message", False) and mid is not None:
        return {"message_thread_id": mid}
    return {}


async def _secret_forward_then_send_with_spoiler(context, message, from_chat_id: str, message_id: int) -> bool:
    """
    У copyMessage в Bot API нет has_spoiler — размытие даёт только sendPhoto/sendVideo/sendAnimation.
    Делаем forward во временное сообщение в целевом чате, читаем file_id, шлём копию со спойлером,
    удаляем пересланный пост.
    """
    dest = message.chat_id
    th = _forum_thread_kwargs(message)
    try:
        fwd = await context.bot.forward_message(
            chat_id=dest,
            from_chat_id=from_chat_id,
            message_id=message_id,
            disable_notification=True,
            **th,
        )
    except Exception as exc:
        logger.warning("secret: forward failed mid=%s: %s", message_id, exc)
        return False

    caption = fwd.caption
    sent = False
    try:
        if fwd.photo:
            await context.bot.send_photo(
                chat_id=dest,
                photo=fwd.photo[-1].file_id,
                caption=caption,
                has_spoiler=True,
                **th,
            )
            sent = True
        elif fwd.video:
            await context.bot.send_video(
                chat_id=dest,
                video=fwd.video.file_id,
                caption=caption,
                has_spoiler=True,
                **th,
            )
            sent = True
        elif fwd.animation:
            await context.bot.send_animation(
                chat_id=dest,
                animation=fwd.animation.file_id,
                caption=caption,
                has_spoiler=True,
                **th,
            )
            sent = True
    except Exception as exc:
        logger.warning("secret: send with spoiler failed mid=%s: %s", message_id, exc)
        sent = False
    finally:
        try:
            await context.bot.delete_message(chat_id=dest, message_id=fwd.message_id)
        except Exception as exc:
            logger.warning("secret: delete forward failed mid=%s: %s", message_id, exc)

    return sent


async def send_altushka_picture(update, context) -> bool:
    """
    Случайный пост из канала «альтушки» (copy_message). Нужны ALTGIRLS_SOURCE_CHANNEL и ALTGIRLS_POST_IDS в .env.
    """
    message = update.effective_message
    if not message:
        return False

    channel = context.bot_data.get("ALTGIRLS_SOURCE_CHANNEL", "").strip()
    message_ids = context.bot_data.get("ALTGIRLS_POST_IDS", [])
    if not channel or not message_ids:
        return False
    return await _copy_media_only(update, context, channel, message_ids, media_kind="picture")


async def send_random_picture(update, context) -> None:
    message = update.effective_message
    if not message:
        return

    channel = context.bot_data.get("MEME_SOURCE_CHANNEL", "").strip()
    message_ids = context.bot_data.get("MEME_POST_IDS", [])
    if await _copy_media_only(update, context, channel, message_ids, media_kind="picture"):
        return

    if context.bot_data.get("ALLOW_URL_FALLBACK", False):
        await message.reply_photo(photo=pick_picture())
    else:
        await message.reply_text(
            "Мемы временно недоступны. Добавь в .env корректные MEME_POST_IDS — я смогу тянуть посты из канала."
        )


async def send_secret_spoiler_from_channel(update, context) -> None:
    """
    Случайный пост из SECRET_SOURCE_CHANNEL с размытием (спойлер).
    copyMessage не умеет has_spoiler — для фото/видео/GIF используется forward + send* + delete.
    Настраивается в .env: SECRET_SOURCE_CHANNEL, SECRET_POST_IDS. Бот должен быть админом канала.
    """
    message = update.effective_message
    if not message:
        return

    channel = context.bot_data.get("SECRET_SOURCE_CHANNEL", "").strip()
    message_ids = context.bot_data.get("SECRET_POST_IDS", [])
    if not channel or not message_ids:
        await message.reply_text(
            "🔒 /secret не настроен. В .env укажи SECRET_SOURCE_CHANNEL (@канал или -100…) "
            "и SECRET_POST_IDS (id постов). Мне нужны права админа в канале.\n\n"
            "🔒 /secret не налаштовано. У .env: SECRET_SOURCE_CHANNEL та SECRET_POST_IDS. Мені потрібні права адміна в каналі."
        )
        return

    probe_attempts = int(context.bot_data.get("MEDIA_PROBE_ATTEMPTS", 1))
    max_rounds = min(max(probe_attempts, 22), max(len(message_ids) * 3, 22))

    for _ in range(max_rounds):
        candidate = choice(message_ids)
        if await _secret_forward_then_send_with_spoiler(context, message, channel, candidate):
            return
        try:
            await context.bot.copy_message(
                chat_id=message.chat_id,
                from_chat_id=channel,
                message_id=candidate,
                caption="",
            )
            await message.reply_text(
                "ℹ️ Без спойлера: для этого поста не фото/видео/GIF в смысле API, либо мне нельзя переслать в чат.\n\n"
                "ℹ️ Без спойлера: це не фото/відео/GIF для API або в чаті заборонено пересилання."
            )
            return
        except Exception as exc_plain:
            logger.warning("secret: plain copy failed mid=%s: %s", candidate, exc_plain)
            continue

    await message.reply_text(
        "🔒 У меня не вышло скопировать пост. Проверь:\n"
        "• SECRET_SOURCE_CHANNEL — @username или -100… канала, где я админ\n"
        "• SECRET_POST_IDS — реальные id постов (есть в канале)\n"
        "• пост не удалён; для альбомов иногда нужны отдельные id\n\n"
        "🔒 У мене не вийшло скопіювати. Перевір SECRET_SOURCE_CHANNEL, SECRET_POST_IDS і мої права в каналі."
    )


async def send_random_gif(update, context) -> None:
    message = update.effective_message
    if not message:
        return

    channel = context.bot_data.get("GIF_SOURCE_CHANNEL", "").strip()
    message_ids = context.bot_data.get("GIF_POST_IDS", [])
    if await _copy_media_only(update, context, channel, message_ids, media_kind="gif"):
        return

    await message.reply_text(
        "GIF только из твоего канала (GIF_SOURCE_CHANNEL). У меня не вышло скопировать пост — "
        "проверь GIF_POST_IDS в .env и что я — админ канала с правом публикации.\n\n"
        "GIF лише з твого каналу. У мене не вийшло скопіювати — перевір GIF_POST_IDS і що я — адмін каналу."
    )


async def send_random_music(update, context) -> None:
    """Случайный пост из MUSIC_SOURCE_CHANNEL (аудио/голосовые документы и т.п.) через copy_message."""
    message = update.effective_message
    if not message:
        return

    channel = context.bot_data.get("MUSIC_SOURCE_CHANNEL", "").strip()
    message_ids = context.bot_data.get("MUSIC_POST_IDS", [])
    if not channel or not message_ids:
        await message.reply_text(
            "🎵 Укажи в .env: MUSIC_SOURCE_CHANNEL=@muzlovonie и MUSIC_POST_IDS — id постов с музыкой "
            "(ссылки вида https://t.me/muzlovonie/123 → число 123). Можно набрать id через "
            "/scan_channel music <ссылки>.\n\n"
            "🎵 У .env: MUSIC_SOURCE_CHANNEL та MUSIC_POST_IDS. Або /scan_channel music <посилання>."
        )
        return

    if await _copy_media_only(update, context, channel, message_ids, media_kind="audio"):
        return

    await message.reply_text(
        "🎵 У меня не вышло скопировать пост. Проверь MUSIC_POST_IDS, что я — админ канала и id "
        "указывают на существующие посты с аудио.\n\n"
        "🎵 У мене не вийшло скопіювати. Перевір MUSIC_POST_IDS і мої права в каналі."
    )
