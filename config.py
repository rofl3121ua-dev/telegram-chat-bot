import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    moderate_links: bool
    random_reply_chance: float
    random_fake_mute_chance: float
    random_media_chance: float
    gif_source_channel: str
    meme_source_channel: str
    gif_post_ids: list[int]
    meme_post_ids: list[int]
    secret_source_channel: str
    secret_post_ids: list[int]
    altgirls_source_channel: str
    altgirls_post_ids: list[int]
    music_source_channel: str
    music_post_ids: list[int]
    allow_url_fallback: bool
    auto_reply_mode: int  # 1 off, 2 every Nth message per user, 3 every message
    autoreply_every_n: int  # режим 2: відповідь кожне N-е повідомлення від того самого користувача
    media_probe_attempts: int
    auto_gif_replies_enabled: bool
    bot_owner_username: str
    random_reaction_chance: float
    random_reaction_cooldown_sec: int


POST_LINK_RE = re.compile(r"https?://t\.me/[A-Za-z0-9_]+/(\d+)")
# Публичный канал: https://t.me/name или https://t.me/name/42 — не путать с t.me/c/… (приватный)
_T_ME_PUBLIC_CHANNEL_RE = re.compile(
    r"^https?://t\.me/([A-Za-z][A-Za-z0-9_]{3,})(?:/.*)?$",
    re.IGNORECASE,
)
_T_ME_PUBLIC_SHORT_RE = re.compile(
    r"^t\.me/([A-Za-z][A-Za-z0-9_]{3,})(?:/.*)?$",
    re.IGNORECASE,
)


def _normalize_source_channel(raw: str) -> str:
    """
    Bot API для from_chat_id принимает @username или -100…, не полный URL.
    Пример: https://t.me/my_channel → @my_channel
    Приватные ссылки вида https://t.me/c/12345/6 не преобразуются — задай -100… вручную.
    """
    s = raw.strip()
    if not s:
        return s
    if re.fullmatch(r"-?\d+", s):
        return s
    if s.startswith("@"):
        return s
    m = _T_ME_PUBLIC_CHANNEL_RE.match(s) or _T_ME_PUBLIC_SHORT_RE.match(s)
    if m:
        return "@" + m.group(1)
    return s


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_int_list(name: str) -> list[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    result: list[int] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        link_match = POST_LINK_RE.search(token)
        if link_match:
            result.append(int(link_match.group(1)))
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            try:
                start = int(left.strip())
                end = int(right.strip())
            except ValueError:
                start = end = None
            if start is not None and end is not None:
                lo, hi = (start, end) if start <= end else (end, start)
                result.extend(range(lo, hi + 1))
                continue
        try:
            result.append(int(token))
        except ValueError:
            continue
    return sorted(set(result))


def _env_owner_username() -> str:
    raw = os.getenv("BOT_OWNER_USERNAME", "rofl3121").strip().lstrip("@")
    return raw.split()[0] if raw else "rofl3121"


def _env_auto_reply_mode() -> int:
    """AUTO_REPLY_MODE=1|2|3 или устаревший AUTO_REPLY_ENABLED (true→3, false→1).

    Если ни AUTO_REPLY_MODE, ни AUTO_REPLY_ENABLED не заданы — режим 2 (не спамить «на каждое»).
    Раньше при пустом .env получался режим 3 из-за AUTO_REPLY_ENABLED по умолчанию True.
    """
    raw = (os.getenv("AUTO_REPLY_MODE") or "").strip().lower()
    if raw in {"1", "off", "none", "mute", "silent"}:
        return 1
    if raw in {"2", "every6", "six", "6", "every10", "ten", "10"}:
        return 2
    if raw in {"3", "on", "all", "every", "always"}:
        return 3
    if raw:
        try:
            n = int(raw)
            if n in {1, 2, 3}:
                return n
        except ValueError:
            pass
    legacy = os.getenv("AUTO_REPLY_ENABLED")
    if legacy is not None and legacy.strip() != "":
        return 3 if _env_bool("AUTO_REPLY_ENABLED", False) else 1
    return 2


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не найден в .env")

    return Settings(
        bot_token=token,
        moderate_links=_env_bool("MODERATE_LINKS", True),
        random_reply_chance=_env_float("RANDOM_REPLY_CHANCE", 0.2),
        random_fake_mute_chance=_env_float("RANDOM_FAKE_MUTE_CHANCE", 0.04),
        random_media_chance=_env_float("RANDOM_MEDIA_CHANCE", 0.13),
        gif_source_channel=_normalize_source_channel(
            os.getenv("GIF_SOURCE_CHANNEL", "@potyznigif").strip()
        ),
        meme_source_channel=_normalize_source_channel(
            os.getenv("MEME_SOURCE_CHANNEL", "@UaReichUa").strip()
        ),
        gif_post_ids=_env_int_list("GIF_POST_IDS"),
        meme_post_ids=_env_int_list("MEME_POST_IDS"),
        secret_source_channel=_normalize_source_channel(os.getenv("SECRET_SOURCE_CHANNEL", "").strip()),
        secret_post_ids=_env_int_list("SECRET_POST_IDS"),
        altgirls_source_channel=_normalize_source_channel(
            os.getenv("ALTGIRLS_SOURCE_CHANNEL", "https://t.me/aigenaltgirls").strip()
        ),
        altgirls_post_ids=_env_int_list("ALTGIRLS_POST_IDS"),
        music_source_channel=_normalize_source_channel(
            os.getenv("MUSIC_SOURCE_CHANNEL", "https://t.me/muzlovonie").strip()
        ),
        music_post_ids=_env_int_list("MUSIC_POST_IDS"),
        allow_url_fallback=_env_bool("ALLOW_URL_FALLBACK", False),
        auto_reply_mode=_env_auto_reply_mode(),
        autoreply_every_n=max(1, min(500, _env_int("AUTOREPLY_EVERY_N", 10))),
        media_probe_attempts=max(1, _env_int("MEDIA_PROBE_ATTEMPTS", 3)),
        auto_gif_replies_enabled=_env_bool("AUTO_GIF_REPLIES_ENABLED", False),
        bot_owner_username=_env_owner_username(),
        random_reaction_chance=max(0.0, min(1.0, _env_float("RANDOM_REACTION_CHANCE", 0.055))),
        random_reaction_cooldown_sec=max(0, _env_int("RANDOM_REACTION_COOLDOWN_SEC", 90)),
    )
