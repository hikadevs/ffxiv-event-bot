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

    @app_commands.command(
        name="link",
        description="Link your Discord account to an FFXIV character.",
    )
    @app_commands.describe(
        name="The character's full name.",
    )
    async def link(
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

        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            await interaction.followup.send(
                "The database is not available. Please try again later.",
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

        character = results[0]

        await database.save_character_link(
            discord_user_id=interaction.user.id,
            lodestone_id=character.lodestone_id,
            character_name=character.name,
            world=character.world,
            data_center=character.data_center,
        )

        await interaction.followup.send(
            f"Linked your Discord account to "
            f"**{character.name}** - "
            f"{character.world} [{character.data_center}].",
            ephemeral=True,
        )

    @app_commands.command(
        name="me",
        description="Show your linked FFXIV character.",
    )
    async def me(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            thinking=True,
            ephemeral=True,
        )

        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            await interaction.followup.send(
                "The database is not available. Please try again later.",
                ephemeral=True,
            )
            return

        character = await database.get_character_link(
            interaction.user.id
        )

        if character is None:
            await interaction.followup.send(
                "You do not have a linked FFXIV character yet. "
                "Use `/character link` first.",
                ephemeral=True,
            )
            return

        session = getattr(
            self.bot,
            "html_session",
            None,
        )

        if session is None:
            await interaction.followup.send(
                "The bot is not ready to handle requests yet. "
                "Please try again later.",
                ephemeral=True,
            )
            return

        lodestone = LodestoneClient(session)

        try:
            profile = await lodestone.get_character_profile(
                character["lodestone_id"]
            )
        except LodestoneError:
            await interaction.followup.send(
                "I found your linked character, but I couldn't "
                "retrieve the Lodestone profile right now.",
                ephemeral=True,
            )
            return

        profile_url = (
            "https://na.finalfantasyxiv.com/lodestone/character/"
            f"{profile.lodestone_id}/"
        )

        embed = discord.Embed(
            title=profile.name,
            url=profile_url,
            description="Linked Final Fantasy XIV character.",
        )

        embed.add_field(
            name="World",
            value=profile.world,
            inline=True,
        )

        embed.add_field(
            name="Data Center",
            value=profile.data_center,
            inline=True,
        )

        embed.add_field(
            name="Lodestone ID",
            value=str(profile.lodestone_id),
            inline=False,
        )

        if profile.portrait_url is not None:
            embed.set_thumbnail(
                url=profile.portrait_url
            )

        embed.add_field(
            name="Race",
            value=profile.race,
            inline=True,
        )

        embed.add_field(
            name="Clan",
            value=profile.clan,
            inline=True,
        )

        embed.add_field(
            name="Gender",
            value=profile.gender,
            inline=True,
        )

        embed.add_field(
            name="Nameday",
            value=profile.nameday,
            inline=False,
        )

        embed.add_field(
            name="Guardian",
            value=profile.guardian,
            inline=False,
        )

        if profile.city_state is not None:
            embed.add_field(
                name="City-state",
                value=profile.city_state,
                inline=True,
            )

        if profile.grand_company is not None:
            embed.add_field(
                name="Grand Company",
                value=profile.grand_company,
                inline=False,
            )

        embed.set_footer(
            text="Aetheryte Events"
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="unlink",
        description="Unlink your FFXIV character from your Discord account.",
    )
    async def unlink(
        self,
        interaction: discord.Interaction,
    ) -> None:
        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            await interaction.response.send_message(
                "The database is not available. Please try again later.",
                ephemeral=True,
            )
            return

        deleted = await database.delete_character_link(
            interaction.user.id
        )

        if not deleted:
            await interaction.response.send_message(
                "You do not currently have a linked FFXIV character.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Your FFXIV character has been unlinked.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Character(bot))