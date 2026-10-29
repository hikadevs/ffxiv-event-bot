import discord
from discord import app_commands
from discord.ext import commands


HELP_TEXT = (
    "Use the bot like this:\n\n"
    "1. `/character search <character name>` to find your FFXIV character.\n"
    "2. `/character link <character name>` to link it to your Discord account.\n"
    "3. `/character me` to confirm your linked character and view job levels.\n"
    "4. `/event create` to create an event, or click the `Join` button on an existing event post.\n"
    "5. `/event roster` or the event details button to see who has signed up."
)


class General(commands.Cog):
    """General commands for the bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="ping",
        description="Check the bot's latency.",
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        """Responds with the bot's latency."""
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong! Latency: {latency_ms} ms",
            ephemeral=True,
        )

    @app_commands.command(
        name="help",
        description="Show instructions for using the bot.",
    )
    async def help(self, interaction: discord.Interaction) -> None:
        """Show how to link a character and sign up for events."""
        embed = discord.Embed(
            title="FFXIV Event Bot Help",
            description=HELP_TEXT,
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Need to join an event?",
            value=(
                "Use `/character search <name>`, then `/character link <name>`. "
                "After that, click `Join` on the event post."
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Sets up the General cog."""
    await bot.add_cog(General(bot))