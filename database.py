from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg

import config


pool: Optional[asyncpg.Pool] = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    captcha_solved BOOLEAN DEFAULT FALSE,
    captcha_fails INTEGER DEFAULT 0,
    captcha_locked_until TIMESTAMPTZ,
    greeted BOOLEAN DEFAULT FALSE,
    blocked_until TIMESTAMPTZ,
    blocked_reason TEXT,
    muted_until TIMESTAMPTZ,
    is_fluder BOOLEAN DEFAULT FALSE,
    total_messages INTEGER DEFAULT 0,
    flood_messages INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_seen TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admins (
    user_id BIGINT PRIMARY KEY,
    nickname TEXT,
    level INTEGER DEFAULT 50,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    content_type TEXT,
    text TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_invites (
    code TEXT PRIMARY KEY,
    created_by BIGINT,
    level INTEGER DEFAULT 50,
    used_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT now(),
    used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_messages_user_created
ON messages(user_id, created_at DESC);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def init_db():
    global pool

    if pool is None:
        pool = await asyncpg.create_pool(
            config.DATABASE_URL,
            min_size=1,
            max_size=10,
        )

    await pool.execute(SCHEMA)


async def close():
    global pool

    if pool is not None:
        await pool.close()
        pool = None


async def ping() -> Optional[int]:
    if pool is None:
        return None

    import time

    started = time.perf_counter()
    await pool.fetchval("SELECT 1")
    return int((time.perf_counter() - started) * 1000)


async def ensure_owner():
    if not config.OWNER_ID:
        return

    await pool.execute(
        """
        INSERT INTO admins (user_id, level, added_by)
        VALUES ($1, 100, $1)
        ON CONFLICT (user_id) DO UPDATE
        SET level = 100
        """,
        config.OWNER_ID,
    )

    await pool.execute(
        """
        UPDATE admins
        SET level = 50
        WHERE level = 100
          AND user_id <> $1
        """,
        config.OWNER_ID,
    )


async def upsert_user(tg_user):
    await pool.execute(
        """
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE
        SET username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            last_seen = now()
        """,
        tg_user.id,
        tg_user.username,
        tg_user.first_name,
        tg_user.last_name,
    )


async def get_fresh_user(user_id: int):
    row = await pool.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

    if not row:
        return None

    now = _now()
    changed = False

    if row["blocked_until"] and row["blocked_until"] <= now:
        await pool.execute(
            """
            UPDATE users
            SET blocked_until = NULL,
                blocked_reason = NULL,
                is_fluder = FALSE
            WHERE user_id = $1
              AND blocked_until <= $2
            """,
            user_id,
            now,
        )
        changed = True

    if row["muted_until"] and row["muted_until"] <= now:
        await pool.execute(
            """
            UPDATE users
            SET muted_until = NULL
            WHERE user_id = $1
              AND muted_until <= $2
            """,
            user_id,
            now,
        )
        changed = True

    if row["captcha_locked_until"] and row["captcha_locked_until"] <= now:
        await pool.execute(
            """
            UPDATE users
            SET captcha_locked_until = NULL,
                captcha_fails = 0
            WHERE user_id = $1
              AND captcha_locked_until <= $2
            """,
            user_id,
            now,
        )
        changed = True

    if changed:
        row = await pool.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

    return row


async def mark_greeted(user_id: int):
    await pool.execute("UPDATE users SET greeted = TRUE WHERE user_id = $1", user_id)


async def solve_captcha(user_id: int):
    await pool.execute(
        """
        UPDATE users
        SET captcha_solved = TRUE,
            captcha_fails = 0,
            captcha_locked_until = NULL
        WHERE user_id = $1
        """,
        user_id,
    )


async def lock_captcha(user_id: int, until: datetime):
    await pool.execute(
        """
        UPDATE users
        SET captcha_fails = 0,
            captcha_locked_until = $2
        WHERE user_id = $1
        """,
        user_id,
        until,
    )


async def get_admin(user_id: int):
    return await pool.fetchrow("SELECT * FROM admins WHERE user_id = $1", user_id)


async def get_admin_level(user_id: int) -> int:
    if config.OWNER_ID and user_id == config.OWNER_ID:
        return 100

    row = await pool.fetchrow("SELECT level FROM admins WHERE user_id = $1", user_id)
    return row["level"] if row else 0


async def set_admin_nickname(user_id: int, nickname: str):
    await pool.execute(
        """
        INSERT INTO admins (user_id, nickname, level)
        VALUES ($1, $2, 50)
        ON CONFLICT (user_id) DO UPDATE
        SET nickname = EXCLUDED.nickname
        """,
        user_id,
        nickname,
    )

    if config.OWNER_ID and user_id == config.OWNER_ID:
        await pool.execute("UPDATE admins SET level = 100 WHERE user_id = $1", user_id)


async def add_admin(user_id: int, added_by: int):
    level = 100 if config.OWNER_ID and user_id == config.OWNER_ID else 50

    await pool.execute(
        """
        INSERT INTO admins (user_id, level, added_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE
        SET level = EXCLUDED.level,
            added_by = EXCLUDED.added_by
        """,
        user_id,
        level,
        added_by,
    )


async def remove_admin(user_id: int) -> bool:
    if config.OWNER_ID and user_id == config.OWNER_ID:
        return False

    result = await pool.execute("DELETE FROM admins WHERE user_id = $1", user_id)
    return result == "DELETE 1"


async def list_admins():
    return await pool.fetch(
        """
        SELECT user_id, nickname, level, created_at
        FROM admins
        ORDER BY level DESC, created_at
        """
    )


async def create_invite(code: str, created_by: int, level: int = 50):
    await pool.execute(
        """
        INSERT INTO admin_invites (code, created_by, level)
        VALUES ($1, $2, $3)
        """,
        code,
        created_by,
        level,
    )


async def activate_invite(code: str, user_id: int) -> bool:
    invite = await pool.fetchrow("SELECT * FROM admin_invites WHERE code = $1", code)

    if not invite or invite["used_at"]:
        return False

    level = invite["level"] or 50
    if config.OWNER_ID and user_id == config.OWNER_ID:
        level = 100

    await pool.execute(
        """
        INSERT INTO admins (user_id, level, added_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE
        SET level = EXCLUDED.level,
            added_by = EXCLUDED.added_by
        """,
        user_id,
        level,
        invite["created_by"],
    )

    await pool.execute(
        """
        UPDATE admin_invites
        SET used_at = now(),
            used_by = $2
        WHERE code = $1
        """,
        code,
        user_id,
    )

    return True


async def get_admin_ids():
    rows = await pool.fetch("SELECT user_id FROM admins")
    return [row["user_id"] for row in rows]


async def block_user(user_id: int, until: datetime, reason: str, is_fluder: bool = False):
    await pool.execute(
        """
        UPDATE users
        SET blocked_until = $2,
            blocked_reason = $3,
            is_fluder = $4
        WHERE user_id = $1
        """,
        user_id,
        until,
        reason,
        is_fluder,
    )


async def apply_antiflood_block(user_id: int, until: datetime):
    await pool.execute(
        """
        UPDATE users
        SET blocked_until = $2,
            blocked_reason = 'antiflood',
            is_fluder = TRUE,
            flood_messages = flood_messages + 10
        WHERE user_id = $1
        """,
        user_id,
        until,
    )


async def unblock_user(user_id: int) -> bool:
    row = await pool.fetchrow(
        """
        UPDATE users
        SET blocked_until = NULL,
            blocked_reason = NULL,
            is_fluder = FALSE
        WHERE user_id = $1
        RETURNING user_id
        """,
        user_id,
    )

    return row is not None


async def mute_user(user_id: int, until: datetime):
    await pool.execute(
        "UPDATE users SET muted_until = $2 WHERE user_id = $1",
        user_id,
        until,
    )


async def unmute_user(user_id: int) -> bool:
    row = await pool.fetchrow(
        """
        UPDATE users
        SET muted_until = NULL
        WHERE user_id = $1
        RETURNING user_id
        """,
        user_id,
    )

    return row is not None


async def get_blocked_list(limit: int = 100):
    return await pool.fetch(
        """
        SELECT user_id, blocked_until, blocked_reason
        FROM users
        WHERE blocked_until > now()
        ORDER BY blocked_until DESC
        LIMIT $1
        """,
        limit,
    )


async def get_muted_list(limit: int = 100):
    return await pool.fetch(
        """
        SELECT user_id, muted_until
        FROM users
        WHERE muted_until > now()
        ORDER BY muted_until DESC
        LIMIT $1
        """,
        limit,
    )


async def increment_total_message(user_id: int):
    await pool.execute(
        """
        UPDATE users
        SET total_messages = total_messages + 1,
            last_seen = now()
        WHERE user_id = $1
        """,
        user_id,
    )


async def increment_flood_message(user_id: int, count: int = 1):
    await pool.execute(
        "UPDATE users SET flood_messages = flood_messages + $2 WHERE user_id = $1",
        user_id,
        count,
    )


async def add_message(user_id: int, content_type: str, text: str):
    await pool.execute(
        """
        INSERT INTO messages (user_id, content_type, text)
        VALUES ($1, $2, $3)
        """,
        user_id,
        content_type,
        text,
    )


async def get_last_messages(user_id: int, limit: int = 15):
    return await pool.fetch(
        """
        SELECT content_type, text, created_at
        FROM messages
        WHERE user_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )


async def get_common_stats():
    return await pool.fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM users WHERE NOT is_fluder) AS clean_users,
            (SELECT COALESCE(SUM(total_messages), 0) FROM users WHERE NOT is_fluder) AS clean_messages,
            (SELECT COUNT(*) FROM users WHERE blocked_until > now()) AS blocked_count,
            (SELECT COUNT(*) FROM users WHERE muted_until > now()) AS muted_count,
            (SELECT COUNT(*) FROM admins) AS admins_count
        """
    )


async def get_flood_stats():
    return await pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE is_fluder OR flood_messages > 0) AS flood_users,
            COALESCE(SUM(flood_messages), 0) AS flood_messages,
            COALESCE(SUM(total_messages + flood_messages), 0) AS total_all
        FROM users
        """
    )


async def get_top_flooders(limit: int = 5):
    return await pool.fetch(
        """
        SELECT user_id, flood_messages, total_messages
        FROM users
        WHERE is_fluder OR flood_messages > 0
        ORDER BY flood_messages DESC
        LIMIT $1
        """,
        limit,
    )