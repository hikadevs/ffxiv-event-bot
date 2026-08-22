from dataclasses import dataclass
import os

from dotenv import load_dotenv

@dataclass(frozen=True)
class Settings:
    discord_token: str
    test_guild_id: int


def load_settings() -> Settings:
    load_dotenv()

    discord_token = os.getenv("DISCORD_TOKEN")
    test_guild_id = os.getenv("TEST_GUILD_ID")

    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    discord_token = discord_token.strip()
    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    if not test_guild_id:
        raise RuntimeError("TEST_GUILD_ID is not configured.")

    return Settings(
        discord_token=discord_token,
        test_guild_id=int(test_guild_id),
    )