import discord
from discord import app_commands
from discord.ext import commands

from xivbot.services.lodestone import (
    LodestoneClient,
    LodestoneError,
)


class Character(
    commands.GroupCog,
    group_name="character",
    group_description="Commands related to Final Fantasy XIV characters.",
):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="search",
        description="Search for an FFXIV character.",
    )
    @app_commands.describe(
        name="The character's full name.",
    )
    async def search(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        await interaction.response.defer(
            thinking=True,
            ephemeral=True,
        )

        session = getattr(
            self.bot,
            "html_session",
            None,
        )

        if session is None:
            await interaction.followup.send(
                "The bot is not ready to handle requests yet. Please try again later.",
                ephemeral=True,
            )
            return

        lodestone = LodestoneClient(session)

        try:
            results = await lodestone.search_character(name)
        except LodestoneError:
            await interaction.followup.send(
                "An error occurred while searching for the character. Please try again later.",
                ephemeral=True,
            )
            return

        if not results:
            await interaction.followup.send(
                f"No characters found for '{name}'.",
                ephemeral=True,
            )
            return

        lines = []

        for result in results[:10]:
            lines.append(
                f"**{result.name}** - "
                f"{result.world} [{result.data_center}]"
            )

        message = "\n".join(lines)

        await interaction.followup.send(
            message,
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Character(bot))