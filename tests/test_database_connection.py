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