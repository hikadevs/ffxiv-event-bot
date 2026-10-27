import discord
from discord import app_commands
from discord.ext import commands

from xivbot.services.lodestone import (
    LodestoneClient,
    LodestoneError,
)


class CharacterProfileView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        profile_embed: discord.Embed,
        jobs_embed: discord.Embed,
    ) -> None:
        super().__init__(timeout=300)
        self.user_id = user_id
        self.profile_embed = profile_embed
        self.jobs_embed = jobs_embed

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who ran this command can use these buttons.",
                ephemeral=True,
            )
            return False

        return True

    async def _show_page(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        selected_tab: str,
    ) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.style = (
                    discord.ButtonStyle.primary
                    if item.label == selected_tab
                    else discord.ButtonStyle.secondary
                )

        await interaction.response.edit_message(
            embed=embed,
            view=self,
        )

    @discord.ui.button(
        label="Profile",
        style=discord.ButtonStyle.primary,
    )
    async def profile_tab(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await self._show_page(
            interaction,
            self.profile_embed,
            "Profile",
        )

    @discord.ui.button(
        label="Jobs",
        style=discord.ButtonStyle.secondary,
    )
    async def jobs_tab(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await self._show_page(
            interaction,
            self.jobs_embed,
            "Jobs",
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

            jobs = await lodestone.get_character_jobs(
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

        profile_embed = discord.Embed(
            title=profile.name,
            url=profile_url,
            description=(
                f"**{profile.world}** · {profile.data_center}"
            ),
            color=discord.Color.blurple(),
        )

        if profile.portrait_url is not None:
            profile_embed.set_thumbnail(
                url=profile.portrait_url
            )

        profile_details = [
            f"**Race:** {profile.race} · {profile.clan}",
            f"**Gender:** {profile.gender}",
            f"**Nameday:** {profile.nameday}",
            f"**Guardian:** {profile.guardian}",
        ]

        if profile.city_state is not None:
            profile_details.append(
                f"**City-state:** {profile.city_state}"
            )

        if profile.grand_company is not None:
            profile_details.append(
                f"**Grand Company:** {profile.grand_company}"
            )

        profile_embed.add_field(
            name="Character",
            value="\n".join(profile_details),
            inline=False,
        )

        jobs_embed = discord.Embed(
            title=f"{profile.name} - Jobs",
            url=profile_url,
            description=(
                f"**{profile.world}** · {profile.data_center}"
            ),
            color=discord.Color.blurple(),
        )

        started_jobs = [
            job
            for job in jobs
            if job.level is not None
        ]

        categories = {
            "Tank": [],
            "Healer": [],
            "Melee DPS": [],
            "Physical Ranged DPS": [],
            "Magical Ranged DPS": [],
            "Limited Job": [],
            "Crafter": [],
            "Gatherer": [],
            "Unknown": [],
        }

        for job in started_jobs:
            categories.setdefault(job.category, []).append(job)

        for category, category_jobs in categories.items():
            if not category_jobs:
                continue

            job_lines = "\n".join(
                f"- {job.name} (Lv. {job.level})"
                for job in category_jobs
            )
            jobs_embed.add_field(
                name=category,
                value=job_lines,
                inline=False,
            )

        if not started_jobs:
            jobs_embed.description += (
                "\n\nNo jobs with a level found for this character."
            )

        footer = f"Lodestone ID: {profile.lodestone_id} · Aetheryte Events"
        profile_embed.set_footer(text=footer)
        jobs_embed.set_footer(text=footer)

        view = CharacterProfileView(
            user_id=interaction.user.id,
            profile_embed=profile_embed,
            jobs_embed=jobs_embed,
        )

        await interaction.followup.send(
            embed=profile_embed,
            view=view,
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