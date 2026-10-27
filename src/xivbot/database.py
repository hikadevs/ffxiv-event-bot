from datetime import datetime
from typing import Literal

import asyncpg


SignupResult = Literal[
    "joined",
    "event_missing",
    "role_unavailable",
    "full",
]


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            dsn=self.database_url,
            min_size=1,
            max_size=5,
        )

    async def create_tables(self) -> None:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS character_links (
                discord_user_id BIGINT PRIMARY KEY,
                lodestone_id BIGINT NOT NULL,
                character_name TEXT NOT NULL,
                world TEXT NOT NULL,
                data_center TEXT NOT NULL
            );
            """
        )

        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                creator_id BIGINT NOT NULL,
                title TEXT NOT NULL,
                scheduled_at TIMESTAMPTZ NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'scheduled',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        await self.pool.execute(
            """
            ALTER TABLE events
            ADD COLUMN IF NOT EXISTS min_job_level INTEGER NOT NULL DEFAULT 1
                CHECK (min_job_level BETWEEN 1 AND 100);
            """
        )

        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS event_roles (
                event_id BIGINT NOT NULL REFERENCES events(event_id)
                    ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('Tank', 'Healer', 'DPS')),
                slots INTEGER NOT NULL CHECK (slots >= 0),
                PRIMARY KEY (event_id, role)
            );
            """
        )

        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS event_signups (
                event_id BIGINT NOT NULL REFERENCES events(event_id)
                    ON DELETE CASCADE,
                discord_user_id BIGINT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('Tank', 'Healer', 'DPS')),
                job TEXT NOT NULL,
                job_level INTEGER NOT NULL CHECK (job_level BETWEEN 1 AND 100),
                character_name TEXT NOT NULL,
                world TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (event_id, discord_user_id),
                FOREIGN KEY (event_id, role)
                    REFERENCES event_roles(event_id, role)
            );
            """
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def ping(self) -> int:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        return await self.pool.fetchval("SELECT 1")

    async def save_character_link(
        self,
        discord_user_id: int,
        lodestone_id: int,
        character_name: str,
        world: str,
        data_center: str,
    ) -> None:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        await self.pool.execute(
            """
            INSERT INTO character_links (
                discord_user_id,
                lodestone_id,
                character_name,
                world,
                data_center
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (discord_user_id)
            DO UPDATE SET
                lodestone_id = EXCLUDED.lodestone_id,
                character_name = EXCLUDED.character_name,
                world = EXCLUDED.world,
                data_center = EXCLUDED.data_center;
            """,
            discord_user_id,
            lodestone_id,
            character_name,
            world,
            data_center,
        )

    async def get_character_link(
        self,
        discord_user_id: int,
    ) -> asyncpg.Record | None:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        return await self.pool.fetchrow(
            """
            SELECT
                discord_user_id,
                lodestone_id,
                character_name,
                world,
                data_center
            FROM character_links
            WHERE discord_user_id = $1;
            """,
            discord_user_id,
        )

    async def delete_character_link(
        self,
        discord_user_id: int,
    ) -> bool:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        result = await self.pool.execute(
            """
            DELETE FROM character_links
            WHERE discord_user_id = $1;
            """,
            discord_user_id,
        )
        return result == "DELETE 1"

    async def create_event(
        self,
        guild_id: int,
        creator_id: int,
        title: str,
        scheduled_at: datetime,
        description: str | None,
        tank_slots: int = 0,
        healer_slots: int = 0,
        dps_slots: int = 0,
        min_job_level: int = 1,
    ) -> int:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        if any(not 0 <= slots <= 24 for slots in (
            tank_slots,
            healer_slots,
            dps_slots,
        )):
            raise ValueError("Role slots must be between 0 and 24.")

        if tank_slots + healer_slots + dps_slots > 24:
            raise ValueError("An event cannot have more than 24 role slots.")

        if not 1 <= min_job_level <= 100:
            raise ValueError("Minimum job level must be between 1 and 100.")

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                event_id = await connection.fetchval(
                    """
                    INSERT INTO events (
                        guild_id,
                        creator_id,
                        title,
                        scheduled_at,
                        description,
                        min_job_level
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING event_id;
                    """,
                    guild_id,
                    creator_id,
                    title,
                    scheduled_at,
                    description,
                    min_job_level,
                )

                if event_id is None:
                    raise RuntimeError("Failed to create event.")

                await connection.executemany(
                    """
                    INSERT INTO event_roles (event_id, role, slots)
                    VALUES ($1, $2, $3);
                    """,
                    [
                        (event_id, "Tank", tank_slots),
                        (event_id, "Healer", healer_slots),
                        (event_id, "DPS", dps_slots),
                    ],
                )

        return event_id

    async def get_event(
        self,
        event_id: int,
    ) -> asyncpg.Record | None:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        return await self.pool.fetchrow(
            """
            SELECT
                event_id,
                guild_id,
                creator_id,
                title,
                scheduled_at,
                description,
                min_job_level,
                status,
                created_at
            FROM events
            WHERE event_id = $1;
            """,
            event_id,
        )

    async def get_event_roles(
        self,
        event_id: int,
    ) -> list[asyncpg.Record]:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        return await self.pool.fetch(
            """
            SELECT role, slots
            FROM event_roles
            WHERE event_id = $1
            ORDER BY CASE role
                WHEN 'Tank' THEN 1
                WHEN 'Healer' THEN 2
                ELSE 3
            END;
            """,
            event_id,
        )

    async def join_event(
        self,
        event_id: int,
        discord_user_id: int,
        role: str,
        job: str,
        job_level: int,
        character_name: str,
        world: str,
    ) -> SignupResult:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                event_record = await connection.fetchrow(
                    """
                    SELECT event_id
                    FROM events
                    WHERE event_id = $1
                    FOR UPDATE;
                    """,
                    event_id,
                )

                if event_record is None:
                    return "event_missing"

                role_record = await connection.fetchrow(
                    """
                    SELECT slots
                    FROM event_roles
                    WHERE event_id = $1 AND role = $2
                    FOR UPDATE;
                    """,
                    event_id,
                    role,
                )

                if role_record is None:
                    return "role_unavailable"

                if role_record["slots"] == 0:
                    return "role_unavailable"

                occupied_slots = await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM event_signups
                    WHERE event_id = $1
                        AND role = $2
                        AND discord_user_id != $3;
                    """,
                    event_id,
                    role,
                    discord_user_id,
                )

                if occupied_slots >= role_record["slots"]:
                    return "full"

                await connection.execute(
                    """
                    INSERT INTO event_signups (
                        event_id,
                        discord_user_id,
                        role,
                        job,
                        job_level,
                        character_name,
                        world
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (event_id, discord_user_id)
                    DO UPDATE SET
                        role = EXCLUDED.role,
                        job = EXCLUDED.job,
                        job_level = EXCLUDED.job_level,
                        character_name = EXCLUDED.character_name,
                        world = EXCLUDED.world;
                    """,
                    event_id,
                    discord_user_id,
                    role,
                    job,
                    job_level,
                    character_name,
                    world,
                )

                return "joined"

    async def get_event_signups(
        self,
        event_id: int,
    ) -> list[asyncpg.Record]:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        return await self.pool.fetch(
            """
            SELECT
                discord_user_id,
                role,
                job,
                job_level,
                character_name,
                world
            FROM event_signups
            WHERE event_id = $1
            ORDER BY CASE role
                WHEN 'Tank' THEN 1
                WHEN 'Healer' THEN 2
                ELSE 3
            END, created_at, discord_user_id;
            """,
            event_id,
        )