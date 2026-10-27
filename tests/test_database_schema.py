from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from xivbot.database import Database


class AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_create_tables_creates_events_table() -> None:
    database = Database("postgresql://unused")
    pool = AsyncMock()
    database.pool = pool

    await database.create_tables()

    executed_sql = [
        call.args[0]
        for call in pool.execute.await_args_list
    ]
    assert any("CREATE TABLE IF NOT EXISTS events" in sql for sql in executed_sql)
    assert any("CREATE TABLE IF NOT EXISTS character_links" in sql for sql in executed_sql)
    assert any("CREATE TABLE IF NOT EXISTS event_roles" in sql for sql in executed_sql)
    assert any(
        "CREATE TABLE IF NOT EXISTS event_signups" in sql
        for sql in executed_sql
    )
    assert any("ADD COLUMN IF NOT EXISTS post_channel_id" in sql for sql in executed_sql)
    assert any("ADD COLUMN IF NOT EXISTS post_message_id" in sql for sql in executed_sql)


@pytest.mark.asyncio
async def test_save_character_link_does_not_create_events_table() -> None:
    database = Database("postgresql://unused")
    pool = AsyncMock()
    database.pool = pool

    await database.save_character_link(
        discord_user_id=123,
        lodestone_id=456,
        character_name="Test Character",
        world="Gilgamesh",
        data_center="Aether",
    )

    assert pool.execute.await_count == 1
    assert "INSERT INTO character_links" in pool.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_create_event_returns_inserted_id() -> None:
    database = Database("postgresql://unused")
    connection = AsyncMock()
    connection.fetchval.return_value = 42
    connection.transaction = lambda: AsyncContext(None)
    pool = SimpleNamespace(
        acquire=lambda: AsyncContext(connection),
    )
    database.pool = pool

    event_id = await database.create_event(
        guild_id=123,
        creator_id=456,
        title="Test event",
        scheduled_at=datetime.now(timezone.utc),
        description=None,
    )

    assert event_id == 42
    assert "RETURNING event_id" in connection.fetchval.await_args.args[0]
    connection.executemany.assert_awaited_once()
    assert [
        (42, "Tank", 0),
        (42, "Healer", 0),
        (42, "DPS", 0),
    ] == connection.executemany.await_args.args[1]


@pytest.mark.asyncio
async def test_get_event_fetches_by_id() -> None:
    database = Database("postgresql://unused")
    pool = AsyncMock()
    database.pool = pool

    await database.get_event(42)

    assert "FROM events" in pool.fetchrow.await_args.args[0]
    assert pool.fetchrow.await_args.args[1] == 42


@pytest.mark.asyncio
async def test_leave_event_deletes_user_signup() -> None:
    database = Database("postgresql://unused")
    connection = AsyncMock()
    connection.fetchrow.return_value = {"event_id": 42}
    connection.execute.return_value = "DELETE 1"
    connection.transaction = lambda: AsyncContext(None)
    database.pool = SimpleNamespace(
        acquire=lambda: AsyncContext(connection),
    )

    result = await database.leave_event(42, 123)

    assert result == "left"
    assert "DELETE FROM event_signups" in connection.execute.await_args.args[0]
    assert connection.execute.await_args.args[1:] == (42, 123)


@pytest.mark.asyncio
async def test_leave_event_reports_when_user_is_not_signed_up() -> None:
    database = Database("postgresql://unused")
    connection = AsyncMock()
    connection.fetchrow.return_value = {"event_id": 42}
    connection.execute.return_value = "DELETE 0"
    connection.transaction = lambda: AsyncContext(None)
    database.pool = SimpleNamespace(
        acquire=lambda: AsyncContext(connection),
    )

    assert await database.leave_event(42, 123) == "not_signed_up"


@pytest.mark.asyncio
async def test_get_published_events_returns_saved_message_ids() -> None:
    database = Database("postgresql://unused")
    pool = AsyncMock()
    database.pool = pool

    await database.get_published_events()

    assert "WHERE post_message_id IS NOT NULL" in pool.fetch.await_args.args[0]
