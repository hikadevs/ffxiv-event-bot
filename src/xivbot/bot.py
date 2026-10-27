import logging

import aiohttp

import discord
from discord.ext import commands

from .config import Settings
from .database import Database


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

#Adding a database connection to the bot class so we can use it for storing and retrieving data later

        self.database = Database(settings.database_url)

#Adding aiohttp client session to the bot class so we can use it for making HTTP requests later

        self.html_session: aiohttp.ClientSession | None = None



#setup_hook asynconously sets up the bots commands after login but before WebSocket events.

    async def setup_hook(self) -> None:
        self.html_session = aiohttp.ClientSession()

# Connecting to the database before syncing commands to ensure that the bot has access to any necessary data during command execution.

        await self.database.connect()
        await self.database.create_tables()

# Loading Cog before syncing commands to ensure that all commands are registered and available for use.

        await self.load_extension("xivbot.cogs.general")
        await self.load_extension("xivbot.cogs.character")
        await self.load_extension("xivbot.cogs.event")

        test_guild = discord.Object(id=self.settings.test_guild_id)

        self.tree.copy_global_to(guild=test_guild)
        prepared = self.tree.get_commands(guild=test_guild)
        logger.info(
            "Prepared guild commands: %s",
            [command.qualified_name for command in prepared],
        )
        synced = await self.tree.sync(guild=test_guild)

#await involves waiting and allows Python to asynchronously run other functions while not slowing down the program.

        logger.info(
            "Discord returned guild commands: %s",
            [command.name for command in synced],
        )
        logger.info(
            "Synced %s top-level command(s) to test guild %s.",
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

# Added Error Handler to catch any errors that occur during command execution and log them for debugging purposes. This helps in identifying issues with the bot's commands and provides feedback to the user when an error occurs.

    async def on_app_command_error(
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

# Closing the aiohttp client session when the bot is shutting down to free up resources and prevent memory leaks. This ensures that any open connections are properly closed and cleaned up before the bot exits.
    async def close(self) -> None:
        await self.database.close()

        if self.html_session is not None:
            await self.html_session.close()

        await super().close()

def create_bot(settings: Settings) -> XIVEventBot:
    bot = XIVEventBot(settings)
    return bot