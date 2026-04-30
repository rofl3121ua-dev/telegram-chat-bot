import logging
import os
from urllib.parse import urlparse, urlunparse

from telegram import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from telegram.ext import Application

from config import load_settings
from handlers import register_handlers
from handlers.poop import start_poop_background
from log_buffer import RingBufferHandler


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
# Reduce noisy polling/network logs in terminal.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

_ring = RingBufferHandler()
_ring.setLevel(logging.INFO)
_ring.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
logging.getLogger().addHandler(_ring)


RU_COMMANDS = [
    BotCommand("start", "Запуск"),
    BotCommand("help", "Помощь"),
    BotCommand("lang", "Выбрать язык"),
    BotCommand("pictures", "Случайная картинка"),
    BotCommand("altushka", "Фото альтушки раз в 10 с"),
    BotCommand("gif", "Случайная GIF"),
    BotCommand("randomgif", "Случайная GIF"),
    BotCommand("music", "Случайный трек с канала"),
    BotCommand("pokushat", "Съесть рандом"),
    BotCommand("eat", "Eat random"),
    BotCommand("pilsl", "Сброс кулдауна еды"),
    BotCommand("datedu", "Админ: выдать еду в инвентарь"),
    BotCommand("obosrat", "Обосрать участника"),
    BotCommand("ip", "Шуточный скан участника"),
    BotCommand("kakapair", "Случайная пара в статистике"),
    BotCommand("mystat", "Моя статистика / профиль"),
    BotCommand("force_poop", "Форс для админа"),
    BotCommand("pokakat", "Владелец: заставить покакать"),
    BotCommand("logs", "Владелец: буфер логов (личка)"),
    BotCommand("ip_reset", "Владелец: сброс IP-досье"),
    BotCommand("autoreply", "Режим: 1 молчит 2 каждое 10-е 3 каждое"),
]

UK_COMMANDS = [
    BotCommand("start", "Запуск"),
    BotCommand("help", "Допомога"),
    BotCommand("lang", "Обрати мову"),
    BotCommand("pictures", "Випадкова картинка"),
    BotCommand("altushka", "Фото альтушки раз на 10 с"),
    BotCommand("gif", "Випадкова GIF"),
    BotCommand("randomgif", "Випадкова GIF"),
    BotCommand("music", "Випадковий трек з каналу"),
    BotCommand("pokushat", "З'їсти рандом"),
    BotCommand("eat", "Eat random"),
    BotCommand("pilsl", "Скидання кулдауна їжі"),
    BotCommand("datedu", "Адмін: видати їжу в інвентар"),
    BotCommand("obosrat", "Обісрати учасника"),
    BotCommand("ip", "Жартівливий скан учасника"),
    BotCommand("kakapair", "Випадкова пара в статистиці"),
    BotCommand("mystat", "Моя статистика / профиль"),
    BotCommand("force_poop", "Форс для адміна"),
    BotCommand("pokakat", "Власник: змусити покакати"),
    BotCommand("logs", "Власник: буфер логів (личка)"),
    BotCommand("ip_reset", "Власник: скидання IP-досьє"),
    BotCommand("autoreply", "Режим: 1 тиша 2 кожне 10-е 3 кожне"),
]


async def _post_init(app: Application) -> None:
    await start_poop_background(app)
    # За замовчуванням українські підписи; для клієнтів з російською мовою інтерфейсу — RU_COMMANDS.
    await app.bot.set_my_commands(UK_COMMANDS)
    await app.bot.set_my_commands(UK_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await app.bot.set_my_commands(UK_COMMANDS, scope=BotCommandScopeAllGroupChats())
    await app.bot.set_my_commands(UK_COMMANDS, language_code="uk")
    await app.bot.set_my_commands(UK_COMMANDS, scope=BotCommandScopeAllPrivateChats(), language_code="uk")
    await app.bot.set_my_commands(UK_COMMANDS, scope=BotCommandScopeAllGroupChats(), language_code="uk")
    await app.bot.set_my_commands(RU_COMMANDS, language_code="ru")
    await app.bot.set_my_commands(RU_COMMANDS, scope=BotCommandScopeAllPrivateChats(), language_code="ru")
    await app.bot.set_my_commands(RU_COMMANDS, scope=BotCommandScopeAllGroupChats(), language_code="ru")

    # Текст у картці бота (інфо) — про зміну настрою залежно від часу доби
    try:
        await app.bot.set_my_short_description(
            "Меми, GIF, жарти та діалог. Відповідаю жіночим лицем; настрій реплік залежить від пори доби."
        )
        await app.bot.set_my_short_description(
            "Мемы, GIF, шутки и разговор. Отвечаю в женском лице; настроение реплик зависит от времени суток.",
            language_code="ru",
        )
        await app.bot.set_my_description(
            "Чат-бот для групи й лички: меми, GIF, жартівлива механіка, випадкові репліки. "
            "Говорю від першої особи, жіночим лицем — тон і настрій у діалозі змінюються залежно від часу доби (ранок, день, вечір і ніч)."
        )
        await app.bot.set_my_description(
            "Чат-бот для групп и лички: мемы, GIF, шуточная механика, случайные реплики. "
            "Говорю от первого лица, в женском роде — тон и настроение в переписке меняются в зависимости от времени суток (утро, день, вечер и ночь).",
            language_code="ru",
        )
    except Exception as exc:
        logger.warning("set_my_description: %s", exc)


def build_app() -> Application:
    settings = load_settings()
    app = Application.builder().token(settings.bot_token).build()
    app.bot_data["MODERATE_LINKS"] = settings.moderate_links
    app.bot_data["RANDOM_REPLY_CHANCE"] = settings.random_reply_chance
    app.bot_data["RANDOM_FAKE_MUTE_CHANCE"] = settings.random_fake_mute_chance
    app.bot_data["RANDOM_MEDIA_CHANCE"] = settings.random_media_chance
    app.bot_data["GIF_SOURCE_CHANNEL"] = settings.gif_source_channel
    app.bot_data["MEME_SOURCE_CHANNEL"] = settings.meme_source_channel
    app.bot_data["GIF_POST_IDS"] = settings.gif_post_ids
    app.bot_data["MEME_POST_IDS"] = settings.meme_post_ids
    app.bot_data["SECRET_SOURCE_CHANNEL"] = settings.secret_source_channel
    app.bot_data["SECRET_POST_IDS"] = settings.secret_post_ids
    app.bot_data["ALTGIRLS_SOURCE_CHANNEL"] = settings.altgirls_source_channel
    app.bot_data["ALTGIRLS_POST_IDS"] = settings.altgirls_post_ids
    app.bot_data["MUSIC_SOURCE_CHANNEL"] = settings.music_source_channel
    app.bot_data["MUSIC_POST_IDS"] = settings.music_post_ids
    app.bot_data["ALLOW_URL_FALLBACK"] = settings.allow_url_fallback
    app.bot_data["AUTO_REPLY_MODE"] = settings.auto_reply_mode
    app.bot_data["AUTOREPLY_EVERY_N"] = settings.autoreply_every_n
    app.bot_data["MEDIA_PROBE_ATTEMPTS"] = settings.media_probe_attempts
    app.bot_data["AUTO_GIF_REPLIES_ENABLED"] = settings.auto_gif_replies_enabled
    app.bot_data["BOT_OWNER_USERNAME"] = settings.bot_owner_username
    app.bot_data["RANDOM_REACTION_CHANCE"] = settings.random_reaction_chance
    app.bot_data["RANDOM_REACTION_COOLDOWN_SEC"] = settings.random_reaction_cooldown_sec
    register_handlers(app)
    app.post_init = _post_init
    return app


def main() -> None:
    application = build_app()
    use_webhook = os.getenv("USE_WEBHOOK", "").strip().lower() in {"1", "true", "yes", "on"}
    if use_webhook:
        raw = os.getenv("WEBHOOK_URL", "").strip()
        if not raw:
            raise RuntimeError(
                "USE_WEBHOOK=1: укажи WEBHOOK_URL — полный https://… адрес вебхука "
                "(как в Bot API setWebhook), например https://host.com/telegram"
            )
        path_override = os.getenv("WEBHOOK_PATH", "").strip().lstrip("/")
        parsed = urlparse(raw)
        if parsed.path and parsed.path != "/":
            path_seg = parsed.path.strip("/")
            public_url = raw
        elif path_override:
            path_seg = path_override
            public_url = urlunparse((parsed.scheme, parsed.netloc, "/" + path_seg, "", "", ""))
        else:
            path_seg = "telegram"
            public_url = urlunparse((parsed.scheme, parsed.netloc, "/" + path_seg, "", "", ""))
        port = int(os.getenv("PORT", "8080"))
        listen = os.getenv("WEBHOOK_LISTEN", "0.0.0.0").strip() or "0.0.0.0"
        logger.info("Webhook: listen %s:%s url_path=%s public=%s", listen, port, path_seg, public_url)
        application.run_webhook(
            listen=listen,
            port=port,
            url_path=path_seg,
            webhook_url=public_url,
            drop_pending_updates=True,
        )
    else:
        logger.info("Bot is running (polling)...")
        application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
