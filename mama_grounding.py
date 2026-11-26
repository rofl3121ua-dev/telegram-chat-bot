"""
Grounded replies for mama-persona factual / ranking questions.

When the user asks Hot mamy («мать» / «мама») for ranked chat facts
(toxic top, active users, etc.), answers MUST come from real stored
stats — never invented handles or roast lore. Thin or missing data →
honest «нет данных».
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

RankKind = Literal["toxic", "active"]

# Address the mama persona (start of message or standalone vocative).
_MAMA_ADDRESS_RE = re.compile(
    r"(?i)(?:^|[\s,.:;!?])(?:мать|мама|мам|hot\s*mamy|hotmamy|mami)\b"
)

# «топ 10», «top 5», «десятку», bare «топ» → limit
_TOP_N_RE = re.compile(
    r"(?i)(?:топ(?:[- ]?а)?|top)\s*(\d{1,2})|"
    r"\b(\d{1,2})\s*(?:топ|мест|человек|людей|користувач|пользовател)|"
    r"\bдесятк[ауеи]?\b"
)

_TOXIC_RE = re.compile(
    r"(?i)токсич|toxic|змей|змій|душнил|скандал|токсик"
)
_ACTIVE_RE = re.compile(
    r"(?i)активн|active| хто\s+пише|кто\s+пишет|писак|message\s*count|"
    r"за\s+актив|по\s+актив|топ\s+актив|active\s+user"
)
# Ranking / list request shape (even without «топ N»).
_RANK_SHAPE_RE = re.compile(
    r"(?i)(?:топ|top|рейтинг|лідерборд|лидерборд|leaderboard|"
    r"состав|список|перелік|ranking|rank)"
)


@dataclass(frozen=True)
class RankIntent:
    kind: RankKind
    limit: int
    addressed_mama: bool


def _normalize(text: str) -> str:
    return (text or "").strip()


def is_mama_addressed(text: str) -> bool:
    return bool(_MAMA_ADDRESS_RE.search(_normalize(text)))


def _parse_limit(text: str, default: int = 10) -> int:
    m = _TOP_N_RE.search(text)
    if not m:
        return default
    if m.group(0).lower().startswith("десят") or "десят" in m.group(0).lower():
        return 10
    raw = m.group(1) or m.group(2)
    if not raw:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    return max(1, min(20, n))


def detect_rank_intent(text: str) -> Optional[RankIntent]:
    """
    Detect factual ranking asks about this chat.

    Triggers when the message looks like a ranked/list request about
    toxicity or activity. Mama address is preferred but not required when
    the ranking shape + topic are clear (avoids inventing via any fallback).
    """
    raw = _normalize(text)
    if not raw:
        return None
    mama = is_mama_addressed(raw)
    toxic = bool(_TOXIC_RE.search(raw))
    active = bool(_ACTIVE_RE.search(raw))
    ranked = bool(_RANK_SHAPE_RE.search(raw)) or bool(_TOP_N_RE.search(raw))

    if not (toxic or active):
        return None
    # Need a ranking/list cue, or mama + clear topic («мать кто токсичнее»).
    if not ranked and not mama:
        return None

    low = raw.lower()
    if toxic and active:
        # Whichever topic appears first wins.
        t_pos = low.find("токси")
        if t_pos < 0:
            t_pos = low.find("toxic")
        a_pos = low.find("актив")
        if a_pos < 0:
            a_pos = low.find("active")
        if a_pos >= 0 and (t_pos < 0 or a_pos < t_pos):
            kind: RankKind = "active"
        else:
            kind = "toxic"
    elif toxic:
        kind = "toxic"
    else:
        kind = "active"

    return RankIntent(kind=kind, limit=_parse_limit(raw), addressed_mama=mama)


def _db_conn():
    # Live app uses handlers.poop DB; import lazily to avoid circular import at load.
    from handlers.poop import _conn, init_db

    init_db()
    return _conn()


def record_message_activity(
    chat_id: int,
    user_id: int,
    *,
    username: Optional[str] = None,
    display_name: Optional[str] = None,
) -> None:
    """Bump per-chat message counters used for «топ активных»."""
    if chat_id == 0 or user_id <= 0:
        return
    label = ""
    if username:
        label = f"@{username.lstrip('@')}"
    elif display_name:
        label = display_name.strip()
    else:
        label = f"id:{user_id}"
    try:
        with _db_conn() as conn:
            conn.execute(
                """
                INSERT INTO chat_message_stats
                    (chat_id, user_id, display_name, message_count, last_seen_ts)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    message_count = message_count + 1,
                    last_seen_ts = excluded.last_seen_ts,
                    display_name = CASE
                        WHEN excluded.display_name != '' AND excluded.display_name NOT LIKE 'id:%'
                        THEN excluded.display_name
                        ELSE chat_message_stats.display_name
                    END
                """,
                (chat_id, user_id, label, time.time()),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_message_activity failed: %s", exc)


def _label_map_from_profiles(conn: sqlite3.Connection, chat_id: int) -> dict[int, str]:
    labels: dict[int, str] = {}
    rows = conn.execute(
        """
        SELECT user_id, shit_received_json, shit_given_json
        FROM poop_profiles WHERE chat_id = ?
        """,
        (chat_id,),
    ).fetchall()
    for user_id, shit_recv_raw, shit_given_raw in rows:
        for blob in (shit_recv_raw, shit_given_raw):
            try:
                data = json.loads(blob or "{}")
            except json.JSONDecodeError:
                continue
            names = data.get("names") if isinstance(data, dict) else None
            if not isinstance(names, dict):
                continue
            for uid_s, name in names.items():
                try:
                    uid = int(uid_s)
                except (TypeError, ValueError):
                    continue
                n = str(name or "").strip()
                if n and uid not in labels:
                    labels[uid] = n
    # Activity table labels
    for uid, name in conn.execute(
        "SELECT user_id, display_name FROM chat_message_stats WHERE chat_id = ?",
        (chat_id,),
    ).fetchall():
        n = str(name or "").strip()
        if n:
            labels[int(uid)] = n
    return labels


def toxic_top_from_db(chat_id: int, limit: int = 10) -> list[tuple[str, int]]:
    """
    Toxicity proxy: total /obosrat (shit_given) actions by each user in this chat.
    Real counters only — empty list if nobody has stats.
    """
    with _db_conn() as conn:
        labels = _label_map_from_profiles(conn, chat_id)
        rows = conn.execute(
            "SELECT user_id, shit_given_json FROM poop_profiles WHERE chat_id = ?",
            (chat_id,),
        ).fetchall()
        scores: dict[int, int] = {}
        for user_id, shit_given_raw in rows:
            try:
                data = json.loads(shit_given_raw or "{}")
            except json.JSONDecodeError:
                continue
            counts = data.get("counts") if isinstance(data, dict) else None
            if not isinstance(counts, dict):
                # legacy flat map
                if isinstance(data, dict) and data and all(isinstance(v, int) for v in data.values()):
                    counts = data
                else:
                    continue
            total = sum(int(v) for v in counts.values())
            if total <= 0:
                continue
            uid = int(user_id)
            scores[uid] = scores.get(uid, 0) + total
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:limit]
        out: list[tuple[str, int]] = []
        for uid, score in ranked:
            out.append((labels.get(uid, f"id:{uid}"), score))
        return out


def active_top_from_db(chat_id: int, limit: int = 10) -> list[tuple[str, int]]:
    """Most messages seen by the bot in this chat (persisted counters)."""
    with _db_conn() as conn:
        rows = conn.execute(
            """
            SELECT display_name, message_count, user_id
            FROM chat_message_stats
            WHERE chat_id = ? AND message_count > 0
            ORDER BY message_count DESC, user_id ASC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()
        out: list[tuple[str, int]] = []
        for name, cnt, uid in rows:
            label = str(name or "").strip() or f"id:{uid}"
            out.append((label, int(cnt)))
        return out


def _intro(lang: str, kind: RankKind, has_data: bool) -> str:
    if lang == "uk":
        if not has_data:
            if kind == "toxic":
                return (
                    "Хотіла б накинути місцевих змій, але в базі немає даних по токсичності "
                    "(лічильники /obosrat порожні). Вигадувати ніки й історії не буду."
                )
            return (
                "Хотіла б скласти топ активних, але я ще не накопичила статистики повідомлень у цьому чаті. "
                "Без цифр — без списку."
            )
        if kind == "toxic":
            return (
                "Ок, слухаю. Ось топ за реальними /obosrat у цьому чаті "
                "(хто кого «обосрав» за статистикою бота) — не вигаданий роаст:"
            )
        return "Ок. Ось топ за кількістю повідомлень, які я реально бачила в цьому чаті:"
    # ru
    if not has_data:
        if kind == "toxic":
            return (
                "Хотела бы накидать местных змей, но в базе нет данных по токсичности "
                "(счётчики /obosrat пусты). Выдумывать ники и истории не буду."
            )
        return (
            "Хотела бы собрать топ активных, но я ещё не накопила статистики сообщений в этом чате. "
            "Без цифр — без списка."
        )
    if kind == "toxic":
        return (
            "Ок, слушаю. Вот топ по реальным /obosrat в этом чате "
            "(кто кого «обосрал» по статистике бота) — не выдуманный роаст:"
        )
    return "Ок. Вот топ по числу сообщений, которые я реально видела в этом чате:"


def _metric_word(lang: str, kind: RankKind, score: int) -> str:
    if lang == "uk":
        if kind == "toxic":
            return f"{score}× /obosrat"
        return f"{score} повід."
    if kind == "toxic":
        return f"{score}× /obosrat"
    return f"{score} сообщ."


def format_rank_reply(lang: str, kind: RankKind, rows: list[tuple[str, int]]) -> str:
    intro = _intro(lang, kind, has_data=bool(rows))
    if not rows:
        return intro
    lines = [intro, ""]
    for i, (label, score) in enumerate(rows, start=1):
        lines.append(f"{i}. {label} — {_metric_word(lang, kind, score)}")
    if lang == "uk":
        lines.append("")
        lines.append("Якщо цифр мало — це вся доступна статистика, без домислів.")
    else:
        lines.append("")
        lines.append("Если цифр мало — это вся доступная статистика, без домыслов.")
    return "\n".join(lines)


def build_grounded_rank_reply(lang: str, chat_id: int, intent: RankIntent) -> str:
    if intent.kind == "toxic":
        rows = toxic_top_from_db(chat_id, intent.limit)
    else:
        rows = active_top_from_db(chat_id, intent.limit)
    return format_rank_reply(lang, intent.kind, rows)
