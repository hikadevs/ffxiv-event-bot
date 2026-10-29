from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from xivbot.bot import XIVEventBot
from xivbot.config import Settings


@pytest.mark.asyncio
async def test_setup_hook_syncs_test_guild_and_global_commands(monkeypatch) -> None:
    guild_id = 123456789
    bot = XIVEventBot(
        Settings(
            discord_token="test-token",
            test_guild_id=guild_id,
            database_url="postgresql://unused",
        )
    )
    bot.database.connect = AsyncMock()
    bot.database.create_tables = AsyncMock()
    bot.load_extension = AsyncMock()
    bot.tree.sync = AsyncMock(
        return_value=[SimpleNamespace(name="ping")]
    )

    # Do not open real HTTP sessions or contact Discord during this unit test.
    session = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr("xivbot.bot.aiohttp.ClientSession", lambda: session)

    try:
        await bot.setup_hook()

        bot.database.connect.assert_awaited_once()
        bot.database.create_tables.assert_awaited_once()
        assert bot.load_extension.await_count == 3
        assert bot.tree.sync.await_count == 2

        test_guild_sync, global_sync = bot.tree.sync.await_args_list
        assert test_guild_sync.args == ()
        assert test_guild_sync.kwargs["guild"].id == guild_id
        assert global_sync == call()
    finally:
        await bot.close()

    session.close.assert_awaited_once()
