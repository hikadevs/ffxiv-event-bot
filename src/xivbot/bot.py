import logging

import discord
from discord.ext import commands

from .config import Settings


logger = logging.getLogger(__name__)

#Creating a custom bot class to handle events and commands

class XIVEventBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()

#Sets up the normal Discord bot with the command prefix and intents first

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
        )

#Adding our own configuration settings to the bot class so we can access them later

        self.settings = settings



#setup_hook asynconously sets up the bots commands after login but before WebSocket events.

    async def setup_hook(self) -> None:
        await self.load_extension("xivbot.cogs.general")

        test_guild = discord.Object(id=self.settings.test_guild_id)

        self.tree.copy_global_to(guild=test_guild)
        synced = await self.tree.sync(guild=test_guild)

#await involves waiting and allows Python to asynchronously run other functions while not slowing down the program.

        logger.info(
            "Synced %s command(s) to test guild %s.",
            len(synced),
            self.settings.test_guild_id,
        )

#async function can perform operations that take time to complete, such as network requests or database queries. Without freezing the entire program.
#on_ready is an event handler that sends a ready message when client is logged in and ready to use. It is called once after the bot has successfully connected to Discord and is ready to start receiving events.
    async def on_ready(self) -> None:
        if self.user is None:
            return

        logger.info(
            "Logged in as %s (ID: %s)",
            self.user,
            self.user.id,
            )


    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        logger.exception(
            "Application command failed.",
            exc_info=error,
        )

        message = "An error occurred while processing the command."

        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )


def create_bot(settings: Settings) -> XIVEventBot:
    bot = XIVEventBot(settings)
    return bot