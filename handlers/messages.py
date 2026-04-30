import logging
import random
import re
import time
from random import choice
from typing import Optional

from telegram import ChatMember, Update
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import ContextTypes, MessageHandler, filters

from content import (
    EDGE_REPLIES_RU,
    EDGE_REPLIES_UK,
    FAKE_MUTE_LINES_RU,
    FAKE_MUTE_LINES_UK,
    ROAST_REPLIES_RU,
    ROAST_REPLIES_UK,
    get_random_reply_pool,
    send_random_gif,
)
from i18n import detect_lang, t
from smart_replies import match_smart_reply

from .commands import execute_altushka

_ALTUSHKA_NEEDLES = (
    "альтушка",
    "альтушку",
    "альтушки",
    "альтушке",
    "altushka",
    "алтушка",
)


def _is_altushka_keyword(text: str) -> bool:
    low = text.lower()
    return any(n in low for n in _ALTUSHKA_NEEDLES)


_WORD_TOKENS_RE = re.compile(r"\w+", re.UNICODE)
# Индексы чата: с какой долей всплывает шутка на «да» / «нет».
_DA_NET_JOKE_CHANCE = 0.22


def _message_word_set(text: str) -> set[str]:
    return set(_WORD_TOKENS_RE.findall(text.lower()))


logger = logging.getLogger(__name__)
GIF_INTERVAL_MIN = 2
GIF_INTERVAL_MAX = 5
MEMORY_TEXT_LIMIT = 80
MEMORY_MEDIA_LIMIT = 40
MIMIC_COOLDOWN_SEC = 35
# Редкі реакції на повідомлення в групах (Telegram Bot API setMessageReaction).
_STAMP_REACTION_EMOJIS = ("💩", "🍓", "🍌")
KAKAPAIR_POOL_MAX = 100


def _touch_kakapair_user(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Хто писав у чат — кандидати для /kakapair (унікальні id, новіші в кінці)."""
    if user_id <= 0:
        return
    lst: list[int] = context.chat_data.setdefault("kakapair_recent_users", [])
    try:
        lst.remove(user_id)
    except ValueError:
        pass
    lst.append(user_id)
    if len(lst) > KAKAPAIR_POOL_MAX:
        context.chat_data["kakapair_recent_users"] = lst[-KAKAPAIR_POOL_MAX:]


async def _maybe_stamp_message_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Інколи ставить одну реакцію на текст учасника — рідко, без серій підряд."""
    if int(context.bot_data.get("AUTO_REPLY_MODE", 2)) == 1:
        return
    chance = float(context.bot_data.get("RANDOM_REACTION_CHANCE", 0.055))
    if chance <= 0 or random.random() >= chance:
        return
    cooldown = int(context.bot_data.get("RANDOM_REACTION_COOLDOWN_SEC", 90))
    now = time.time()
    if cooldown > 0 and (now - float(context.chat_data.get("bot_reaction_last_ts", 0.0))) < cooldown:
        return

    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or not message.from_user or message.from_user.is_bot:
        return
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    emoji = random.choice(_STAMP_REACTION_EMOJIS)
    try:
        await context.bot.set_message_reaction(
            chat.id,
            message.message_id,
            reaction=[emoji],
        )
        context.chat_data["bot_reaction_last_ts"] = now
    except TelegramError as exc:
        logger.debug("set_message_reaction: %s", exc)


def _trim_tail(items: list, max_items: int) -> list:
    if len(items) <= max_items:
        return items
    return items[-max_items:]


def _remember_chat_payload(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    memory = context.chat_data.setdefault("chat_memory", {})
    texts = memory.setdefault("texts", [])
    stickers = memory.setdefault("stickers", [])
    photos = memory.setdefault("photos", [])
    animations = memory.setdefault("animations", [])

    if message.text and len(message.text.strip()) >= 4:
        texts.append(message.text.strip())
        memory["texts"] = _trim_tail(texts, MEMORY_TEXT_LIMIT)
    if message.sticker and message.sticker.file_id:
        stickers.append(message.sticker.file_id)
        memory["stickers"] = _trim_tail(stickers, MEMORY_MEDIA_LIMIT)
    if message.photo:
        best = message.photo[-1]
        if best and best.file_id:
            photos.append(best.file_id)
            memory["photos"] = _trim_tail(photos, MEMORY_MEDIA_LIMIT)
    if message.animation and message.animation.file_id:
        animations.append(message.animation.file_id)
        memory["animations"] = _trim_tail(animations, MEMORY_MEDIA_LIMIT)


async def _maybe_mimic_chat(message, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    now = time.monotonic()
    last_ts = float(context.chat_data.get("mimic_last_ts", 0.0))
    if (now - last_ts) < MIMIC_COOLDOWN_SEC:
        return
    memory = context.chat_data.get("chat_memory", {})
    texts = list(memory.get("texts", []))
    stickers = list(memory.get("stickers", []))
    photos = list(memory.get("photos", []))
    animations = list(memory.get("animations", []))

    # Low chance to avoid flood and keep it funny.
    if random.random() >= 0.065:
        return

    options: list[str] = []
    if texts:
        options.append("text")
    if stickers:
        options.append("sticker")
    if photos:
        options.append("photo")
    if animations:
        options.append("animation")
    if not options:
        return

    picked = random.choice(options)
    try:
        if picked == "text":
            line = random.choice(texts)
            await message.reply_text(line)
        elif picked == "sticker":
            await message.reply_sticker(random.choice(stickers))
        elif picked == "photo":
            await message.reply_photo(random.choice(photos))
        else:
            await message.reply_animation(random.choice(animations))
        context.chat_data["mimic_last_ts"] = now
    except Exception as exc:  # noqa: BLE001
        logger.debug("Mimic reply failed: %s", exc)


def _bump_autoreply_seq_mode2(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """У режимі 2 лічимо текстові повідомлення окремо для кожного користувача (кожне N-е від нього)."""
    if int(context.bot_data.get("AUTO_REPLY_MODE", 2)) != 2:
        return
    if user_id <= 0:
        return
    by_user: dict[int, int] = context.chat_data.setdefault("autoreply_seq_by_user", {})
    by_user[user_id] = int(by_user.get(user_id, 0)) + 1


def _generic_autoreply_fire(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Чи запускати випадкові/рост/пайплайн (не стосується розумних відповідей — вони йдуть окремо)."""
    mode = int(context.bot_data.get("AUTO_REPLY_MODE", 2))
    if mode == 1:
        return False
    if mode == 3:
        return True
    if user_id <= 0:
        return False
    n = max(1, int(context.bot_data.get("AUTOREPLY_EVERY_N", 10)))
    seq = int(context.chat_data.get("autoreply_seq_by_user", {}).get(user_id, 0))
    return seq % n == 0


async def _run_autoreply_pipeline(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message,
    lang: str,
    mode: int,
) -> None:
    """GIF-інтервал + репліки. Режими 2 і 3 — одна гарантована фраза з пулу на цей заход (на 6-му повідомленні / завжди). Режим «старого» випадкового барражу лишається лише як fallback для невідомого mode."""
    auto_gif_replies_enabled = context.bot_data.get("AUTO_GIF_REPLIES_ENABLED", False)

    gif_target = context.chat_data.get("gif_every_n")
    if not isinstance(gif_target, int) or gif_target < GIF_INTERVAL_MIN or gif_target > GIF_INTERVAL_MAX:
        gif_target = random.randint(GIF_INTERVAL_MIN, GIF_INTERVAL_MAX)
        context.chat_data["gif_every_n"] = gif_target
        context.chat_data["gif_counter"] = 0

    gif_counter = int(context.chat_data.get("gif_counter", 0)) + 1
    context.chat_data["gif_counter"] = gif_counter
    if auto_gif_replies_enabled and gif_counter >= gif_target:
        await send_random_gif(update, context)
        context.chat_data["gif_counter"] = 0
        context.chat_data["gif_every_n"] = random.randint(GIF_INTERVAL_MIN, GIF_INTERVAL_MAX)

    # 2 — кожне N-е від користувача (зовні вже відфільтровано), 3 — кожне: завжди одна відповідь із пулу.
    if mode in (2, 3):
        await message.reply_text(choice(get_random_reply_pool(lang)))
        return

    if context.chat_data.get("edge_mode", False):
        edge_pool = EDGE_REPLIES_UK if lang == "uk" else EDGE_REPLIES_RU
        if random.random() < 0.18:
            await message.reply_text(choice(edge_pool))

    if random.random() < context.bot_data.get("RANDOM_REPLY_CHANCE", 0.2):
        await message.reply_text(choice(get_random_reply_pool(lang)))

    if random.random() < 0.035:
        roast_pool = ROAST_REPLIES_UK if lang == "uk" else ROAST_REPLIES_RU
        await message.reply_text(choice(roast_pool))

    if random.random() < context.bot_data.get("RANDOM_FAKE_MUTE_CHANCE", 0.04):
        user = message.from_user.mention_html() if message.from_user else "user"
        mute_pool = FAKE_MUTE_LINES_UK if lang == "uk" else FAKE_MUTE_LINES_RU
        await message.reply_text(choice(mute_pool).format(user=user), parse_mode="HTML")

    await _maybe_mimic_chat(message, context, lang)


def _extract_link(text: Optional[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(tag in lowered for tag in ("http://", "https://", "t.me/", "telegram.me/"))


def _chat_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    if "lang" in context.chat_data:
        return context.chat_data["lang"]

    text = ""
    if update.effective_message:
        text = update.effective_message.text or update.effective_message.caption or ""
    lang = detect_lang(text)
    context.chat_data["lang"] = lang
    return lang


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.new_chat_members:
        return
    lang = _chat_lang(update, context)
    for member in update.message.new_chat_members:
        await update.message.reply_text(t(lang, "welcome", user=member.mention_html()), parse_mode="HTML")


async def moderate_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.bot_data.get("MODERATE_LINKS", True):
        return
    message = update.message
    if not message or not update.effective_chat or not message.from_user:
        return

    if not (_extract_link(message.text) or _extract_link(message.caption)):
        return

    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, message.from_user.id)
        if member.status in {ChatMember.ADMINISTRATOR, ChatMember.OWNER}:
            return
        await message.delete()
        lang = _chat_lang(update, context)
        mention = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        await context.bot.send_message(update.effective_chat.id, t(lang, "links_only_admins", user=mention))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to moderate links: %s", exc)


async def on_regular_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return

    try:
        if message.from_user and not message.from_user.is_bot:
            _touch_kakapair_user(context, message.from_user.id)
        _remember_chat_payload(message, context)
        text = message.text.lower()
        if not context.chat_data.get("lang_locked", False):
            context.chat_data["lang"] = detect_lang(message.text)
        lang = _chat_lang(update, context)
        if _is_altushka_keyword(message.text):
            await execute_altushka(update, context, lang)
            return

        auto_gif_replies_enabled = context.bot_data.get("AUTO_GIF_REPLIES_ENABLED", False)
        reply_mode = int(context.bot_data.get("AUTO_REPLY_MODE", 2))
        uid = message.from_user.id if message.from_user else 0

        _bump_autoreply_seq_mode2(context, uid)

        # Режим 1 — повна тиша (без розумних відповідей і без випадкового пайплайну).
        if reply_mode == 1:
            return

        smart_line = match_smart_reply(message.text, lang)
        if smart_line:
            await message.reply_text(smart_line)
            return

        if not _generic_autoreply_fire(context, uid):
            return

        if random.random() < _DA_NET_JOKE_CHANCE:
            w = _message_word_set(message.text)
            if "да" in w:
                await message.reply_text("пизда")
                return
            if "нет" in w:
                await message.reply_text("минет")
                return

        if "сосал" in text:
            await message.reply_text(t(lang, "sosal_reply"))
            if auto_gif_replies_enabled:
                await send_random_gif(update, context)
            return

        await _run_autoreply_pipeline(update, context, message, lang, reply_mode)
    finally:
        await _maybe_stamp_message_reaction(update, context)


async def on_any_message_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return
    if message.text:
        # Texts are already processed in on_regular_message to avoid duplicates.
        return
    _remember_chat_payload(message, context)


def register_message_handlers(app) -> None:
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, moderate_links), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_regular_message), group=2)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_any_message_memory), group=3)
