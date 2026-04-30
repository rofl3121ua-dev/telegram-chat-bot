import asyncio
from random import choice
import re
import time
from typing import Optional

from telegram import ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes

from ip_scan import (
    build_ip_dossier_v2,
    format_ip_dossier_caption,
    format_legacy_ip_dossier_caption,
    ip_target_is_bot_owner,
    is_v2_ip_dossier,
    owner_classified_dossier_v2,
    random_ip_scan_photo_url,
    regenerate_ip_dossier_fields_keep_photo,
)
from log_buffer import get_recent_lines

from content import (
    EDGE_REPLIES_RU,
    EDGE_REPLIES_UK,
    PIZDY_LINES_RU,
    PIZDY_LINES_UK,
    send_altushka_picture,
    send_random_gif,
    send_random_music,
    send_random_picture,
    send_secret_spoiler_from_channel,
)

ALTUSHKA_COOLDOWN_SEC = 10
ALTUSHKA_FAKE_GENERATION_SEC = 5.0
_ALTUSHKA_GEN_PCTS = (11, 29, 46, 63, 81, 94)
from .poop import _is_bot_owner, _load_profile, _resolve_target_user, _save_profile, ip_username_candidates
from i18n import detect_lang, t

TG_POST_LINK_RE = re.compile(r"https?://t\.me/[A-Za-z0-9_]+/(\d+)")


def _altushka_generation_status(lang: str, pct: int, tick: int) -> str:
    bar_len = 12
    filled = max(0, min(bar_len, round(bar_len * pct / 100)))
    bar = "█" * filled + "░" * (bar_len - filled)
    wave = ("lllllll" * 2)[tick % 7 : (tick % 7) + 7]
    if lang == "uk":
        return f"🎨 Генерую зображення…\n{wave} {bar} {pct}%"
    return f"🎨 Генерирую изображение…\n{wave} {bar} {pct}%"


async def _altushka_fake_generation_then_send(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> bool:
    """Показує фейковий прогрес ~5 с, видаляє повідомлення, потім copy фото з каналу."""
    message = update.effective_message
    if not message:
        return False
    n_steps = len(_ALTUSHKA_GEN_PCTS)
    step_sec = ALTUSHKA_FAKE_GENERATION_SEC / max(1, n_steps - 1)
    status_msg = await message.reply_text(_altushka_generation_status(lang, _ALTUSHKA_GEN_PCTS[0], 0))
    for step in range(1, n_steps):
        await asyncio.sleep(step_sec)
        try:
            await status_msg.edit_text(_altushka_generation_status(lang, _ALTUSHKA_GEN_PCTS[step], step))
        except TelegramError:
            pass
    try:
        await context.bot.delete_message(chat_id=message.chat_id, message_id=status_msg.message_id)
    except TelegramError:
        pass
    return await send_altushka_picture(update, context)


def _chat_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    if "lang" in context.chat_data:
        return context.chat_data["lang"]
    sample = update.effective_message.text if update.effective_message else ""
    lang = detect_lang(sample or "")
    context.chat_data["lang"] = lang
    return lang


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    if chat.type == "private":
        return True
    member = await context.bot.get_chat_member(chat.id, user.id)
    return member.status in {ChatMember.ADMINISTRATOR, ChatMember.OWNER}


async def _can_manage_ip_dossier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """В личке — только владелец бота; в группе — владелец или админы."""
    if _is_bot_owner(update, context):
        return True
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await _is_group_admin(update, context)
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _chat_lang(update, context)
    await update.effective_message.reply_text(t(lang, "start"))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _chat_lang(update, context)
    await update.effective_message.reply_text(t(lang, "help"))


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _chat_lang(update, context)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Русский", callback_data="lang:ru")],
            [InlineKeyboardButton("Українська", callback_data="lang:uk")],
        ]
    )
    await update.effective_message.reply_text(t(lang, "lang_choose"), reply_markup=keyboard)


async def pictures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_random_picture(update, context)


async def gif_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_random_gif(update, context)


async def random_gif_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_random_gif(update, context)


async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_random_music(update, context)


async def execute_altushka(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    """Случайное фото из канала альтушек; не чаще раз в 10 с на чат. Команда /altushka и слово в тексте."""
    message = update.effective_message
    if not message:
        return
    now = time.time()
    last = float(context.chat_data.get("altushka_last_ts", 0.0))
    if now - last < ALTUSHKA_COOLDOWN_SEC:
        wait = max(1, int(ALTUSHKA_COOLDOWN_SEC - (now - last) + 0.99))
        await message.reply_text(
            f"Подожди ~{wait} с перед следующей альтушкой или /altushka."
            if lang == "ru"
            else f"Зачекай ~{wait} с перед наступною альтушкою або /altushka."
        )
        return

    channel = (context.bot_data.get("ALTGIRLS_SOURCE_CHANNEL") or "").strip()
    ids = context.bot_data.get("ALTGIRLS_POST_IDS") or []
    if not channel or not ids:
        await message.reply_text(t(lang, "altushka_not_configured"))
        return

    context.chat_data["altushka_last_ts"] = now
    ok = await _altushka_fake_generation_then_send(update, context, lang)
    if not ok:
        await message.reply_text(t(lang, "altushka_failed"))


async def altushka_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    lang = _chat_lang(update, context)
    await execute_altushka(update, context, lang)


async def secret_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_bot_owner(update, context):
        lang = _chat_lang(update, context)
        await update.effective_message.reply_text(t(lang, "secret_owner_only"))
        return
    await send_secret_spoiler_from_channel(update, context)


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Последние строки логов из памяти — только владелец, только личка."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    lang = _chat_lang(update, context)
    if chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "Логи доступны только в личке с ботом."
            if lang == "ru"
            else "Логи — лише в особистих повідомленнях з ботом."
        )
        return
    if not _is_bot_owner(update, context):
        await message.reply_text(t(lang, "secret_owner_only"))
        return
    n_lines = 100
    if context.args:
        try:
            n_lines = min(500, max(5, int(context.args[0])))
        except ValueError:
            pass
    lines = get_recent_lines(n_lines)
    if not lines:
        await message.reply_text(
            "Буфер логов пуст с момента запуска бота."
            if lang == "ru"
            else "Буфер логів порожній від запуску бота."
        )
        return
    body = "\n".join(lines)
    head = (
        f"Логи (строк: {len(lines)}, запрошено до {n_lines})\n\n"
        if lang == "ru"
        else f"Логи (рядків: {len(lines)}, запитано до {n_lines})\n\n"
    )
    text = head + body
    max_chunk = 4000
    first = True
    for i in range(0, len(text), max_chunk):
        chunk = text[i : i + max_chunk]
        if first:
            await message.reply_text(chunk)
            first = False
        else:
            await context.bot.send_message(chat.id, chunk)


async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Службная «довідка»: ответь на сообщение или /ip @username. Первый скан сохраняется в инвентарь цели."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    lang = _chat_lang(update, context)
    user = await _resolve_target_user(update, context)
    if not user:
        nicks = ip_username_candidates(message, context)
        if nicks:
            tail = ", ".join(f"@{n}" for n in nicks[:3])
            await message.reply_text(
                (
                    f"Мне не удалось найти пользователя по нику ({tail}). Проверь написание — такого username может не быть в Telegram. Либо ответь на сообщение этого человека и отправь `/ip` без ника."
                    if lang == "ru"
                    else f"Не вдалося знайти користувача за ніком ({tail}). Перевір написання — такого username може не бути в Telegram. Або відповідь на повідомлення цієї людини й надішли `/ip` без ніка."
                ),
                parse_mode="Markdown",
            )
        else:
            await message.reply_text(
                "Ответь на сообщение человека или укажи ник: `/ip @username`"
                if lang == "ru"
                else "Відповідай на повідомлення людини або вкажи нік: `/ip @username`",
                parse_mode="Markdown",
            )
        return
    display = f"@{user.username}" if user.username else (user.first_name or str(user.id))
    owner_username = (context.bot_data.get("BOT_OWNER_USERNAME") or "rofl3121").strip()
    target_profile = _load_profile(user.id, chat.id, lang)
    target_profile["chat_id"] = chat.id
    inv = dict(target_profile.get("inventory") or {})
    if ip_target_is_bot_owner(user.username, owner_username):
        new_d = owner_classified_dossier_v2(lang)
        inv["ip_dossier"] = new_d
        target_profile["inventory"] = inv
        _save_profile(target_profile)
        photo_url = str(new_d["photo_url"])
        caption = format_ip_dossier_caption(display, new_d, lang)
        try:
            await message.reply_photo(
                photo=photo_url,
                caption=caption[:1024],
            )
        except TelegramError:
            await message.reply_text(caption[:4096])
        return
    dossier = inv.get("ip_dossier") if isinstance(inv.get("ip_dossier"), dict) else None
    if dossier and is_v2_ip_dossier(dossier):
        photo_url = str(dossier.get("photo_url") or "").strip() or random_ip_scan_photo_url()
        caption = format_ip_dossier_caption(display, dossier, lang)
    elif dossier and str(dossier.get("text", "")).strip():
        photo_url = str(dossier.get("photo_url") or "").strip() or random_ip_scan_photo_url()
        caption = format_legacy_ip_dossier_caption(display, lang)
    else:
        new_d = build_ip_dossier_v2(lang)
        inv["ip_dossier"] = new_d
        target_profile["inventory"] = inv
        _save_profile(target_profile)
        photo_url = str(new_d["photo_url"])
        caption = format_ip_dossier_caption(display, new_d, lang)
    try:
        await message.reply_photo(
            photo=photo_url,
            caption=caption[:1024],
        )
    except TelegramError:
        await message.reply_text(caption[:4096])


async def ip_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сброс закреплённого IP-досье у пользователя — только владелец бота."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    lang = _chat_lang(update, context)
    if not _is_bot_owner(update, context):
        await message.reply_text(t(lang, "secret_owner_only"))
        return
    user = await _resolve_target_user(update, context)
    if not user:
        await message.reply_text(
            "Кому сбросить: ответь на сообщение или `/ip_reset @username`"
            if lang == "ru"
            else "Кому скинути: відповідь або `/ip_reset @username`",
            parse_mode="Markdown",
        )
        return
    profile = _load_profile(user.id, chat.id, lang)
    inv = dict(profile.get("inventory") or {})
    had = "ip_dossier" in inv
    if had:
        del inv["ip_dossier"]
    profile["inventory"] = inv
    profile["chat_id"] = chat.id
    _save_profile(profile)
    if had:
        await message.reply_text(
            "Досье сброшено. Следующий /ip у этой персоны создаст новую запись."
            if lang == "ru"
            else "Досьє скинуто. Наступний /ip для цієї людини згенерує новий запис."
        )
    else:
        await message.reply_text(
            "У пользователя не было закреплённого досье."
            if lang == "ru"
            else "У користувача не було прикріпленого досьє."
        )


async def newip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ группы / владелец: заново сгенерировать поля досье у цели; портрет сохраняется (если уже был v2)."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    lang = _chat_lang(update, context)
    if not await _can_manage_ip_dossier(update, context):
        await message.reply_text(
            "Эта команда доступна админам группы или владельцу бота. В личке с ботом — только владельцу."
            if lang == "ru"
            else "Ця команда доступна адмінам групи або власнику бота. У личці з ботом — лише власнику."
        )
        return
    user = await _resolve_target_user(update, context)
    if not user:
        await message.reply_text(
            "Кому обновить: ответь на сообщение или `/newip @username`"
            if lang == "ru"
            else "Кому оновити: відповідь або `/newip @username`",
            parse_mode="Markdown",
        )
        return
    display = f"@{user.username}" if user.username else (user.first_name or str(user.id))
    owner_username = (context.bot_data.get("BOT_OWNER_USERNAME") or "rofl3121").strip()
    profile = _load_profile(user.id, chat.id, lang)
    profile["chat_id"] = chat.id
    inv = dict(profile.get("inventory") or {})
    if ip_target_is_bot_owner(user.username, owner_username):
        new_d = owner_classified_dossier_v2(lang)
        ok = (
            "Досье владельца: только засекречённый шаблон (ERROR)."
            if lang == "ru"
            else "Досьє власника: лише засекречений шаблон (ERROR)."
        )
        inv["ip_dossier"] = new_d
        profile["inventory"] = inv
        _save_profile(profile)
        photo_url = str(new_d["photo_url"])
        caption = format_ip_dossier_caption(display, new_d, lang)
        try:
            await message.reply_photo(photo=photo_url, caption=f"{ok}\n\n{caption}"[:1024])
        except TelegramError:
            await message.reply_text(f"{ok}\n\n{caption}"[:4096])
        return
    dossier = inv.get("ip_dossier") if isinstance(inv.get("ip_dossier"), dict) else None
    had_v2 = bool(dossier and is_v2_ip_dossier(dossier))
    photo_kept = had_v2 and str(dossier.get("photo_url") or "").strip()
    if had_v2 and photo_kept:
        new_d = regenerate_ip_dossier_fields_keep_photo(lang, photo_kept)
        ok = (
            "Обновила досье (текст). Фото то же."
            if lang == "ru"
            else "Оновила досьє (текст). Фото те саме."
        )
    else:
        new_d = build_ip_dossier_v2(lang)
        ok = (
            "Собрала досье заново (полная генерация)."
            if lang == "ru"
            else "Зібрала досьє заново (повна генерація)."
        )
    inv["ip_dossier"] = new_d
    profile["inventory"] = inv
    _save_profile(profile)
    photo_url = str(new_d["photo_url"])
    caption = format_ip_dossier_caption(display, new_d, lang)
    try:
        await message.reply_photo(photo=photo_url, caption=f"{ok}\n\n{caption}"[:1024])
    except TelegramError:
        await message.reply_text(f"{ok}\n\n{caption}"[:4096])


async def newippic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ группы / владелец: только новый портрет (URL), поля досье те же."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    lang = _chat_lang(update, context)
    if not await _can_manage_ip_dossier(update, context):
        await message.reply_text(
            "Эта команда доступна админам группы или владельцу бота. В личке с ботом — только владельцу."
            if lang == "ru"
            else "Ця команда доступна адмінам групи або власнику бота. У личці з ботом — лише власнику."
        )
        return
    user = await _resolve_target_user(update, context)
    if not user:
        await message.reply_text(
            "Кому сменить фото: ответь на сообщение или `/newippic @username`"
            if lang == "ru"
            else "Кому змінити фото: відповідь або `/newippic @username`",
            parse_mode="Markdown",
        )
        return
    display = f"@{user.username}" if user.username else (user.first_name or str(user.id))
    owner_username = (context.bot_data.get("BOT_OWNER_USERNAME") or "rofl3121").strip()
    profile = _load_profile(user.id, chat.id, lang)
    profile["chat_id"] = chat.id
    inv = dict(profile.get("inventory") or {})
    dossier = inv.get("ip_dossier") if isinstance(inv.get("ip_dossier"), dict) else None
    if ip_target_is_bot_owner(user.username, owner_username):
        new_d = owner_classified_dossier_v2(lang)
        inv["ip_dossier"] = new_d
        profile["inventory"] = inv
        _save_profile(profile)
        caption = format_ip_dossier_caption(display, new_d, lang)
        note = (
            "Портрет владельца: только ERROR (засекречено)."
            if lang == "ru"
            else "Портрет власника: лише ERROR (засекречено)."
        )
        try:
            await message.reply_photo(
                photo=str(new_d["photo_url"]),
                caption=f"{note}\n\n{caption}"[:1024],
            )
        except TelegramError:
            await message.reply_text(f"{note}\n\n{caption}"[:4096])
        return
    if not dossier or not is_v2_ip_dossier(dossier):
        await message.reply_text(
            (
                "Сначала нужно v2-досье: пусть участник получит `/ip`, или используй `/newip`."
                if lang == "ru"
                else "Спочатку потрібне v2-досьє: нехай учасник отримає `/ip`, або використай `/newip`."
            ),
            parse_mode="Markdown",
        )
        return
    old = str(dossier.get("photo_url") or "").strip()
    new_url = random_ip_scan_photo_url(exclude=old or None)
    dossier = dict(dossier)
    dossier["v"] = 2
    dossier["photo_url"] = new_url
    inv["ip_dossier"] = dossier
    profile["inventory"] = inv
    _save_profile(profile)
    caption = format_ip_dossier_caption(display, dossier, lang)
    note = (
        "Портрет в досье заменила."
        if lang == "ru"
        else "Портрет у досьє замінила."
    )
    try:
        await message.reply_photo(photo=new_url, caption=f"{note}\n\n{caption}"[:1024])
    except TelegramError:
        await message.reply_text(f"{note}\n\n{caption}"[:4096])


async def pizdy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _chat_lang(update, context)
    args = context.args
    if not args:
        await update.effective_message.reply_text(t(lang, "pizdy_missing_user"))
        return

    target = args[0]
    template = choice(PIZDY_LINES_UK if lang == "uk" else PIZDY_LINES_RU)
    await update.effective_message.reply_text(template.format(target=target))
    await send_random_gif(update, context)


async def jewnazi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _chat_lang(update, context)
    current = context.chat_data.get("edge_mode", False)
    context.chat_data["edge_mode"] = not current
    await update.effective_message.reply_text(t(lang, "edge_on" if not current else "edge_off"))


async def scan_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Extract message_ids from t.me post links and store them in runtime bot_data.
    Usage:
      /scan_channel gif https://t.me/potyznigif/10 https://t.me/potyznigif/11
      /scan_channel meme https://t.me/UaReichUa/55
    """
    message = update.effective_message
    if not message:
        return

    lang = _chat_lang(update, context)
    if not context.args or len(context.args) < 2:
        await message.reply_text(
            "RU: /scan_channel gif|meme|music|secret|altgirls <ссылки на посты>\n"
            "UK: /scan_channel gif|meme|music|secret|altgirls <посилання на пости>\n\n"
            "Пример:\n"
            "/scan_channel gif https://t.me/potyznigif/10\n"
            "/scan_channel music https://t.me/muzlovonie/5\n"
            "/scan_channel secret https://t.me/your_channel/5"
        )
        return

    mode = context.args[0].lower().strip()
    if mode not in {"gif", "meme", "music", "secret", "altgirls"}:
        await message.reply_text(
            "mode: `gif`, `meme`, `music`, `secret` или `altgirls`.", parse_mode="Markdown"
        )
        return

    links_blob = " ".join(context.args[1:])
    ids = [int(match) for match in TG_POST_LINK_RE.findall(links_blob)]
    if not ids:
        await message.reply_text(
            "Не нашёл message_id в ссылках. Нужен формат: https://t.me/channel_name/123"
            if lang == "ru"
            else "Не знайшов message_id у посиланнях. Потрібен формат: https://t.me/channel_name/123"
        )
        return

    if mode == "gif":
        key = "GIF_POST_IDS"
    elif mode == "secret":
        key = "SECRET_POST_IDS"
    elif mode == "altgirls":
        key = "ALTGIRLS_POST_IDS"
    elif mode == "music":
        key = "MUSIC_POST_IDS"
    else:
        key = "MEME_POST_IDS"
    existing = context.bot_data.get(key, [])
    merged = sorted(set(existing + ids))
    context.bot_data[key] = merged

    await message.reply_text(
        (
            f"Готово. Найдено {len(ids)} id, всего в {key}: {len(merged)}.\n"
            f"Добавь в .env:\n{key}={','.join(str(i) for i in merged)}"
        )
        if lang == "ru"
        else (
            f"Готово. Знайдено {len(ids)} id, всього в {key}: {len(merged)}.\n"
            f"Додай у .env:\n{key}={','.join(str(i) for i in merged)}"
        )
    )


async def autoreply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    lang = _chat_lang(update, context)
    if not await _is_group_admin(update, context):
        await message.reply_text(
            "Только админ может менять автоответ." if lang == "ru" else "Лише адмін може змінювати автовідповідь."
        )
        return

    arg = (context.args[0].lower().strip() if context.args else "status")

    def _parse_autoreply_mode(s: str) -> Optional[int]:
        if s in {"1", "off", "none", "mute", "silent"}:
            return 1
        if s in {"2", "every6", "six", "6", "every10", "ten", "10"}:
            return 2
        if s in {"3", "on", "all", "every", "always"}:
            return 3
        try:
            n = int(s)
            if n in {1, 2, 3}:
                return n
        except ValueError:
            pass
        return None

    if arg == "status":
        m = int(context.bot_data.get("AUTO_REPLY_MODE", 2))
        n = int(context.bot_data.get("AUTOREPLY_EVERY_N", 10))
        if m == 2:
            await message.reply_text(t(lang, "autoreply_status_2", n=n))
        else:
            await message.reply_text(t(lang, f"autoreply_status_{m}"))
        return

    new_mode = _parse_autoreply_mode(arg)
    if new_mode is None:
        n = int(context.bot_data.get("AUTOREPLY_EVERY_N", 10))
        await message.reply_text(t(lang, "autoreply_usage", n=n))
        return

    context.bot_data["AUTO_REPLY_MODE"] = new_mode
    n = int(context.bot_data.get("AUTOREPLY_EVERY_N", 10))
    if new_mode == 2:
        await message.reply_text(t(lang, "autoreply_status_2", n=n))
    else:
        await message.reply_text(t(lang, f"autoreply_status_{new_mode}"))


def register_command_handlers(app) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("pictures", pictures_command))
    app.add_handler(CommandHandler("gif", gif_command))
    app.add_handler(CommandHandler("randomgif", random_gif_command))
    app.add_handler(CommandHandler("music", music_command))
    # Только ASCII: PTB не принимает кириллицу в имени команды. /альтушка — пиши словом в чате.
    app.add_handler(CommandHandler("altushka", altushka_command))
    app.add_handler(CommandHandler("secret", secret_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("ip_reset", ip_reset_command))
    app.add_handler(CommandHandler("newip", newip_command))
    app.add_handler(CommandHandler("newippic", newippic_command))
    app.add_handler(CommandHandler("pizdy", pizdy_command))
    app.add_handler(CommandHandler("jewnazi", jewnazi_command))
    app.add_handler(CommandHandler("scan_channel", scan_channel_command))
    app.add_handler(CommandHandler("autoreply", autoreply_command))
