import discord
from discord import app_commands
from discord.ext import commands

# Creating a group of Discord functions that can be used as commands in the bot. This is a cog, which is a way to organize commands and events in a Discord bot.

class General(commands.Cog):
    """General commands for the bot."""

    def __init__(self, bot: commands.Bot) -> None:

#Stores Reference to the bot instance for use in the cog's commands and events.

        self.bot = bot

    @app_commands.command(
            name="ping", 
            description="Check the bot's latency."
            )
    async def ping(self, interaction: discord.Interaction) -> None:
        """Responds with the bot's latency."""
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong! Latency: {latency_ms} ms"
            )

async def setup(bot: commands.Bot) -> None:
    """Sets up the General cog."""
    await bot.add_cog(General(bot))