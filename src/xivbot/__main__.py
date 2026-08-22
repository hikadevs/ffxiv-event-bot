import logging

import discord

from .bot import create_bot
from .config import load_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )   

    settings = load_settings()
    bot = create_bot(settings)

    try:
        bot.run(settings.discord_token)
    except discord.LoginFailure as error:
        raise RuntimeError(
            "Discord rejected DISCORD_TOKEN. Generate a new bot token in the "
            "Discord Developer Portal and update .env."
        ) from error


if __name__ == "__main__":
    main()