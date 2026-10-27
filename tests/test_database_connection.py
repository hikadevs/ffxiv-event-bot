import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv

from xivbot.database import Database


load_dotenv()


def _test_discord_user_id() -> int:
    return time.time_ns()


@pytest.mark.asyncio
async def test_database_connection() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)

    try:
        await database.connect()

        result = await database.ping()

        assert result == 1
    finally:
        await database.close()

@pytest.mark.asyncio
async def test_save_and_get_character_link() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)
    discord_user_id = _test_discord_user_id()

    try:
        await database.connect()
        await database.create_tables()

        await database.save_character_link(
            discord_user_id=discord_user_id,
            lodestone_id=987654321,
            character_name="Test Character",
            world="Gilgamesh",
            data_center="Aether",
        )

        character = await database.get_character_link(discord_user_id)

        assert character is not None
        assert character["discord_user_id"] == discord_user_id
        assert character["lodestone_id"] == 987654321
        assert character["character_name"] == "Test Character"
        assert character["world"] == "Gilgamesh"
        assert character["data_center"] == "Aether"

    finally:
        if database.pool is not None:
            await database.delete_character_link(discord_user_id)
        await database.close()

@pytest.mark.asyncio
async def test_save_character_link_updates_existing_user() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)
    discord_user_id = _test_discord_user_id()

    try:
        await database.connect()
        await database.create_tables()

        await database.save_character_link(
            discord_user_id=discord_user_id,
            lodestone_id=111111111,
            character_name="First Character",
            world="Gilgamesh",
            data_center="Aether",
        )

        await database.save_character_link(
            discord_user_id=discord_user_id,
            lodestone_id=222222222,
            character_name="Second Character",
            world="Cactuar",
            data_center="Aether",
        )

        character = await database.get_character_link(discord_user_id)

        assert character is not None
        assert character["lodestone_id"] == 222222222
        assert character["character_name"] == "Second Character"
        assert character["world"] == "Cactuar"

    finally:
        if database.pool is not None:
            await database.delete_character_link(discord_user_id)
        await database.close()

@pytest.mark.asyncio
async def test_get_character_link_returns_none_for_unknown_user() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)

    try:
        await database.connect()
        await database.create_tables()

        character = await database.get_character_link(_test_discord_user_id())

        assert character is None

    finally:
        await database.close()

@pytest.mark.asyncio
async def test_delete_character_link() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)
    discord_user_id = _test_discord_user_id()

    try:
        await database.connect()
        await database.create_tables()

        await database.save_character_link(
            discord_user_id=discord_user_id,
            lodestone_id=123456789,
            character_name="Delete Test",
            world="Zalera",
            data_center="Crystal",
        )

        deleted = await database.delete_character_link(
            discord_user_id
        )

        assert deleted is True

        character = await database.get_character_link(
            discord_user_id
        )

        assert character is None

    finally:
        if database.pool is not None:
            await database.delete_character_link(discord_user_id)
        await database.close()

@pytest.mark.asyncio
async def test_delete_unknown_character_link_returns_false() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)

    try:
        await database.connect()
        await database.create_tables()

        deleted = await database.delete_character_link(_test_discord_user_id())

        assert deleted is False

    finally:
        await database.close()

@pytest.mark.asyncio
async def test_create_event() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)

    await database.connect()
    await database.create_tables()

    scheduled_at = (
        datetime.now(timezone.utc)
        + timedelta(days=1)
    )

    event_id: int | None = None

    try:
        event_id = await database.create_event(
            guild_id=111111111,
            creator_id=222222222,
            title="Test Raid Night",
            scheduled_at=scheduled_at,
            description="Testing event creation.",
        )

        assert isinstance(event_id, int)
        assert event_id > 0

        if database.pool is None:
            pytest.fail("Database pool is not connected.")

        event = await database.pool.fetchrow(
            """
            SELECT
                event_id,
                guild_id,
                creator_id,
                title,
                scheduled_at,
                description,
                status
            FROM events
            WHERE event_id = $1;
            """,
            event_id,
        )

        assert event is not None
        assert event["guild_id"] == 111111111
        assert event["creator_id"] == 222222222
        assert event["title"] == "Test Raid Night"
        assert event["description"] == "Testing event creation."
        assert event["status"] == "scheduled"

    finally:
        if database.pool is not None and event_id is not None:
            await database.pool.execute(
                """
                DELETE FROM events
                WHERE event_id = $1;
                """,
                event_id,
            )

        await database.close()

@pytest.mark.asyncio
async def test_get_event() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)

    await database.connect()
    await database.create_tables()

    scheduled_at = (
        datetime.now(timezone.utc)
        + timedelta(days=2)
    )

    event_id: int | None = None

    try:
        event_id = await database.create_event(
            guild_id=333333333,
            creator_id=444444444,
            title="Savage Reclears",
            scheduled_at=scheduled_at,
            description="Weekly reclear night.",
        )

        event = await database.get_event(event_id)

        assert event is not None
        assert event["event_id"] == event_id
        assert event["guild_id"] == 333333333
        assert event["creator_id"] == 444444444
        assert event["title"] == "Savage Reclears"
        assert event["description"] == "Weekly reclear night."
        assert event["status"] == "scheduled"

    finally:
        if database.pool is not None and event_id is not None:
            await database.pool.execute(
                """
                DELETE FROM events
                WHERE event_id = $1;
                """,
                event_id,
            )

        await database.close()