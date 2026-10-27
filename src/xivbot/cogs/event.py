from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands

from xivbot.database import SignupResult
from xivbot.services.lodestone import LodestoneClient, LodestoneError


ROLE_CHOICES = [
    app_commands.Choice(name="Tank", value="Tank"),
    app_commands.Choice(name="Healer", value="Healer"),
    app_commands.Choice(name="DPS", value="DPS"),
]

DPS_CATEGORIES = {
    "Melee DPS",
    "Physical Ranged DPS",
    "Magical Ranged DPS",
}


def _local_time_to_utc(
    local_time: datetime,
    local_timezone: ZoneInfo,
) -> datetime:
    candidates: set[datetime] = set()
    for fold in (0, 1):
        localized_time = local_time.replace(
            tzinfo=local_timezone,
            fold=fold,
        )
        utc_time = localized_time.astimezone(dt_timezone.utc)
        if utc_time.astimezone(local_timezone).replace(
            tzinfo=None,
        ) == local_time:
            candidates.add(utc_time)

    if not candidates:
        raise ValueError("This local time does not exist in that timezone.")
    if len(candidates) > 1:
        raise ValueError("This local time is ambiguous in that timezone.")

    return candidates.pop()


class Event(
    commands.GroupCog,
    group_name="event",
    group_description="Commands for creating and managing events.",
):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="create",
        description="Create a new event.",
    )
    @app_commands.describe(
        title="The name of the event.",
        scheduled_at="Local start time. Example: 2026-10-30 20:00",
        timezone="IANA timezone for the local start time. Example: America/New_York",
        description="Optional description for the event.",
        tank_slots="Number of Tank slots.",
        healer_slots="Number of Healer slots.",
        dps_slots="Number of DPS slots.",
        min_job_level="Minimum level required for the selected job.",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        title: str,
        scheduled_at: str,
        timezone: str,
        tank_slots: app_commands.Range[int, 0, 24] = 0,
        healer_slots: app_commands.Range[int, 0, 24] = 0,
        dps_slots: app_commands.Range[int, 0, 24] = 0,
        min_job_level: app_commands.Range[int, 1, 100] = 1,
        description: str | None = None,
    ) -> None:
        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            await interaction.response.send_message(
                "The database is not available.",
                ephemeral=True,
            )
            return

        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Events can only be created inside a Discord server.",
                ephemeral=True,
            )
            return

        if tank_slots + healer_slots + dps_slots > 24:
            await interaction.response.send_message(
                "An event cannot have more than 24 role slots.",
                ephemeral=True,
            )
            return

        try:
            event_time = datetime.strptime(
                scheduled_at,
                "%Y-%m-%d %H:%M",
            )
        except ValueError:
            await interaction.response.send_message(
                "Invalid date format. Use `YYYY-MM-DD HH:MM`.",
                ephemeral=True,
            )
            return

        try:
            local_timezone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            await interaction.response.send_message(
                "Invalid timezone. Use an IANA timezone such as `America/New_York`.",
                ephemeral=True,
            )
            return

        try:
            event_time = _local_time_to_utc(event_time, local_timezone)
        except ValueError as error:
            await interaction.response.send_message(
                f"{error} Choose a different local time.",
                ephemeral=True,
            )
            return

        event_id = await database.create_event(
            guild_id=interaction.guild_id,
            creator_id=interaction.user.id,
            title=title,
            scheduled_at=event_time,
            description=description,
            tank_slots=tank_slots,
            healer_slots=healer_slots,
            dps_slots=dps_slots,
            min_job_level=min_job_level,
        )

        total_slots = tank_slots + healer_slots + dps_slots
        role_summary = (
            f" ({total_slots} slots: {tank_slots} Tank, "
            f"{healer_slots} Healer, {dps_slots} DPS; "
            f"minimum job level {min_job_level})"
            if total_slots
            else ""
        )
        await interaction.response.send_message(
            f"Created event **#{event_id} — {title}** "
            f"for <t:{int(event_time.timestamp())}:F>{role_summary}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="join",
        description="Sign up for an event using your linked character.",
    )
    @app_commands.describe(
        event_id="The event number.",
        role="The role you want to fill.",
        job="The job on your linked character to use.",
    )
    @app_commands.choices(role=ROLE_CHOICES)
    async def join(
        self,
        interaction: discord.Interaction,
        event_id: int,
        role: app_commands.Choice[str],
        job: str,
    ) -> None:
        await interaction.response.defer(
            thinking=True,
            ephemeral=True,
        )

        database = getattr(self.bot, "database", None)
        if database is None:
            await interaction.followup.send(
                "The database is not available.",
                ephemeral=True,
            )
            return

        if interaction.guild_id is None:
            await interaction.followup.send(
                "Event signups are only available inside a Discord server.",
                ephemeral=True,
            )
            return

        event = await database.get_event(event_id)
        if event is None or event["guild_id"] != interaction.guild_id:
            await interaction.followup.send(
                "That event could not be found in this server.",
                ephemeral=True,
            )
            return

        role_slots = await database.get_event_roles(event_id)
        available_slots = {
            entry["role"]: entry["slots"]
            for entry in role_slots
        }
        if available_slots.get(role.value, 0) <= 0:
            await interaction.followup.send(
                f"This event has no {role.value} slots.",
                ephemeral=True,
            )
            return

        character = await database.get_character_link(interaction.user.id)
        if character is None:
            await interaction.followup.send(
                "Link your FFXIV character first with `/character link`.",
                ephemeral=True,
            )
            return

        session = getattr(self.bot, "html_session", None)
        if session is None:
            await interaction.followup.send(
                "The bot is not ready to check your character's jobs.",
                ephemeral=True,
            )
            return

        try:
            jobs = await LodestoneClient(session).get_character_jobs(
                character["lodestone_id"]
            )
        except LodestoneError:
            await interaction.followup.send(
                "I couldn't retrieve your character's jobs from Lodestone. "
                "Please try again later.",
                ephemeral=True,
            )
            return

        selected_job = next(
            (
                available_job
                for available_job in jobs
                if available_job.name.casefold() == job.strip().casefold()
            ),
            None,
        )
        if selected_job is None or selected_job.level is None:
            await interaction.followup.send(
                "That job is not leveled on your linked character. "
                "Choose a job shown by `/character me`.",
                ephemeral=True,
            )
            return

        job_role = (
            "DPS"
            if selected_job.category in DPS_CATEGORIES
            else selected_job.category
        )
        if job_role != role.value:
            await interaction.followup.send(
                f"{selected_job.name} is a {job_role} job, not a "
                f"{role.value} job.",
                ephemeral=True,
            )
            return

        minimum_level = event["min_job_level"]
        if selected_job.level < minimum_level:
            await interaction.followup.send(
                f"{selected_job.name} is level {selected_job.level}; "
                f"this event requires level {minimum_level} or higher.",
                ephemeral=True,
            )
            return

        result: SignupResult = await database.join_event(
            event_id=event_id,
            discord_user_id=interaction.user.id,
            role=role.value,
            job=selected_job.name,
            job_level=selected_job.level,
            character_name=character["character_name"],
            world=character["world"],
        )

        messages = {
            "joined": (
                f"Signed up **{character['character_name']}** "
                f"({selected_job.name}, Lv. {selected_job.level}) "
                f"for **{role.value}** in event **#{event_id}**."
            ),
            "event_missing": "That event could not be found.",
            "role_unavailable": f"This event has no {role.value} slots.",
            "full": f"All {role.value} slots for this event are full.",
        }
        await interaction.followup.send(
            messages[result],
            ephemeral=True,
        )

    @app_commands.command(
        name="roster",
        description="Show an event's role requirements and signups.",
    )
    @app_commands.describe(event_id="The event number.")
    async def roster(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        database = getattr(self.bot, "database", None)
        if database is None:
            await interaction.response.send_message(
                "The database is not available.",
                ephemeral=True,
            )
            return

        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Event rosters are only available inside a Discord server.",
                ephemeral=True,
            )
            return

        event = await database.get_event(event_id)
        if event is None or event["guild_id"] != interaction.guild_id:
            await interaction.response.send_message(
                "That event could not be found in this server.",
                ephemeral=True,
            )
            return

        roles = await database.get_event_roles(event_id)
        signups = await database.get_event_signups(event_id)
        lines: list[str] = []
        for role in roles:
            if role["slots"] == 0:
                continue

            role_signups = [
                signup
                for signup in signups
                if signup["role"] == role["role"]
            ]
            lines.append(
                f"**{role['role']}: "
                f"{len(role_signups)}/{role['slots']}**"
            )
            if role_signups:
                lines.extend(
                    f"<@{signup['discord_user_id']}> — "
                    f"{signup['job']} Lv. {signup['job_level']}"
                    for signup in role_signups
                )
            else:
                lines.append("No signups yet.")

        if not lines:
            lines.append("No role slots have been configured.")

        await interaction.response.send_message(
            f"**Event #{event_id} — {event['title']}**\n"
            + "\n".join(lines),
            ephemeral=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Event(bot))