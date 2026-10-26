from xivbot.config import load_settings


def test_load_settings(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("TEST_GUILD_ID", "123456789")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/test_db",
    )

    settings = load_settings()

    assert settings.discord_token == "test-token"
    assert settings.test_guild_id == 123456789
    assert settings.database_url == (
        "postgresql://user:password@localhost:5432/test_db"
    )