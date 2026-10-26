from dataclasses import dataclass
import os

from dotenv import load_dotenv

@dataclass(frozen=True)
class Settings:
    discord_token: str
    test_guild_id: int
    database_url: str


def load_settings() -> Settings:
    load_dotenv()

    discord_token = os.getenv("DISCORD_TOKEN")
    test_guild_id = os.getenv("TEST_GUILD_ID")
    database_url = os.getenv("DATABASE_URL")

    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    discord_token = discord_token.strip()
    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    if not test_guild_id:
        raise RuntimeError("TEST_GUILD_ID is not configured.")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    return Settings(
        discord_token=discord_token,
        test_guild_id=int(test_guild_id),
        database_url=database_url,
    )