import os

import pytest
from dotenv import load_dotenv

from xivbot.database import Database


load_dotenv()


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

    try:
        await database.connect()
        await database.create_tables()

        await database.save_character_link(
            discord_user_id=123456789,
            lodestone_id=987654321,
            character_name="Test Character",
            world="Gilgamesh",
            data_center="Aether",
        )

        character = await database.get_character_link(123456789)

        assert character is not None
        assert character["discord_user_id"] == 123456789
        assert character["lodestone_id"] == 987654321
        assert character["character_name"] == "Test Character"
        assert character["world"] == "Gilgamesh"
        assert character["data_center"] == "Aether"

    finally:
        await database.close()

@pytest.mark.asyncio
async def test_save_character_link_updates_existing_user() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL is not configured.")

    database = Database(database_url)

    try:
        await database.connect()
        await database.create_tables()

        discord_user_id = 555555555

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

        character = await database.get_character_link(999999999999999999)

        assert character is None

    finally:
        await database.close()