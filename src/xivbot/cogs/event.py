from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from xivbot.database import LeaveResult, SignupResult
from xivbot.models.character import CharacterJob
from xivbot.services.lodestone import LodestoneClient, LodestoneError


logger = logging.getLogger(__name__)


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


def _parse_event_time(local_time: str, timezone: str) -> datetime:
    try:
        parsed_time = datetime.strptime(local_time, "%Y-%m-%d %H:%M")
    except ValueError as error:
        raise ValueError(
            "Invalid date format. Use `YYYY-MM-DD HH:MM`."
        ) from error

    try:
        local_timezone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(
            "Invalid timezone. Use an IANA timezone such as "
            "`America/New_York`."
        ) from error

    try:
        return _local_time_to_utc(parsed_time, local_timezone)
    except ValueError as error:
        raise ValueError(
            f"{error} Choose a different local time."
        ) from error


@dataclass
class EventDraft:
    guild_id: int
    creator_id: int
    channel_id: int
    title: str = ""
    description: str | None = None
    timezone: str | None = None
    scheduled_at: datetime | None = None
    tank_slots: int = 0
    healer_slots: int = 0
    dps_slots: int = 0
    min_job_level: int = 1


class EventWizardView(discord.ui.View):
    def __init__(self, user_id: int) -> None:
        super().__init__(timeout=300)
        self.user_id = user_id

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


class RetryModalView(EventWizardView):
    def __init__(
        self,
        user_id: int,
        modal_factory: Callable[[], discord.ui.Modal],
    ) -> None:
        super().__init__(user_id)
        self.modal_factory = modal_factory

    @discord.ui.button(label="Try again", style=discord.ButtonStyle.primary)
    async def retry(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(self.modal_factory())


class ContinueModalView(EventWizardView):
    def __init__(
        self,
        user_id: int,
        label: str,
        modal_factory: Callable[[], discord.ui.Modal],
    ) -> None:
        super().__init__(user_id)
        self.modal_factory = modal_factory
        self.continue_button.label = label

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(self.modal_factory())


class EventDetailsModal(discord.ui.Modal, title="Event details — Step 1 of 3"):
    event_title = discord.ui.TextInput(
        label="Event name",
        placeholder="E.g. Saturday evening raid",
        max_length=100,
    )
    event_description = discord.ui.TextInput(
        label="Description (optional)",
        placeholder="Add any details attendees should know",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(
        self,
        event_cog: Event,
        draft: EventDraft,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        super().__init__()
        self.event_cog = event_cog
        self.draft = draft
        if title is not None:
            self.event_title.default = title
        if description is not None:
            self.event_description.default = description

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = self.event_title.value.strip()
        if not title:
            await interaction.response.send_message(
                "Enter a name for the event.",
                ephemeral=True,
                view=RetryModalView(
                    self.draft.creator_id,
                    lambda: EventDetailsModal(
                        self.event_cog,
                        self.draft,
                        self.event_title.value,
                        self.event_description.value,
                    ),
                ),
            )
            return

        self.draft.title = title
        self.draft.description = self.event_description.value.strip() or None
        await interaction.response.send_message(
            "Event details saved. Choose the timezone for the event.",
            ephemeral=True,
            view=EventTimezoneView(self.event_cog, self.draft),
        )


TIMEZONE_CHOICES = [
    ("UTC", "UTC"),
    ("New York", "America/New_York"),
    ("Chicago", "America/Chicago"),
    ("Denver", "America/Denver"),
    ("Los Angeles", "America/Los_Angeles"),
    ("Anchorage", "America/Anchorage"),
    ("Phoenix", "America/Phoenix"),
    ("Toronto", "America/Toronto"),
    ("Vancouver", "America/Vancouver"),
    ("Sao Paulo", "America/Sao_Paulo"),
    ("London", "Europe/London"),
    ("Paris", "Europe/Paris"),
    ("Berlin", "Europe/Berlin"),
    ("Helsinki", "Europe/Helsinki"),
    ("Moscow", "Europe/Moscow"),
    ("Johannesburg", "Africa/Johannesburg"),
    ("Dubai", "Asia/Dubai"),
    ("Kolkata", "Asia/Kolkata"),
    ("Bangkok", "Asia/Bangkok"),
    ("Singapore", "Asia/Singapore"),
    ("Tokyo", "Asia/Tokyo"),
    ("Seoul", "Asia/Seoul"),
    ("Shanghai", "Asia/Shanghai"),
    ("Sydney", "Australia/Sydney"),
]


class EventTimezoneView(EventWizardView):
    def __init__(self, event_cog: Event, draft: EventDraft) -> None:
        super().__init__(draft.creator_id)
        self.event_cog = event_cog
        self.draft = draft
        self.timezone_select = discord.ui.Select(
            placeholder="Choose your timezone",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=label, value=timezone)
                for label, timezone in TIMEZONE_CHOICES
            ]
            + [
                discord.SelectOption(
                    label="Other (enter an IANA timezone)",
                    value="other",
                )
            ],
        )
        self.timezone_select.callback = self._select_timezone
        self.add_item(self.timezone_select)

        continue_button = discord.ui.Button(
            label="Continue",
            style=discord.ButtonStyle.primary,
        )
        continue_button.callback = self._continue
        self.add_item(continue_button)

    async def _select_timezone(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer()

    async def _continue(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.timezone_select.values:
            await interaction.response.send_message(
                "Choose a timezone first.",
                ephemeral=True,
            )
            return

        selected_timezone = self.timezone_select.values[0]
        if selected_timezone == "other":
            await interaction.response.send_modal(
                EventTimezoneModal(self.event_cog, self.draft)
            )
            return

        self.draft.timezone = selected_timezone
        await interaction.response.send_modal(
            EventScheduleModal(self.event_cog, self.draft)
        )


class EventTimezoneModal(
    discord.ui.Modal,
    title="Enter your timezone",
):
    timezone = discord.ui.TextInput(
        label="IANA timezone",
        placeholder="America/New_York",
        max_length=100,
    )

    def __init__(self, event_cog: Event, draft: EventDraft) -> None:
        super().__init__()
        self.event_cog = event_cog
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction) -> None:
        timezone = self.timezone.value.strip()
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            await interaction.response.send_message(
                "Invalid timezone. Use an IANA timezone such as "
                "`America/New_York`.",
                ephemeral=True,
                view=RetryModalView(
                    self.draft.creator_id,
                    lambda: EventTimezoneModal(self.event_cog, self.draft),
                ),
            )
            return

        self.draft.timezone = timezone
        await interaction.response.send_message(
            "Timezone saved. Continue to enter the event's local start time.",
            ephemeral=True,
            view=ContinueModalView(
                self.draft.creator_id,
                "Set date and time",
                lambda: EventScheduleModal(self.event_cog, self.draft),
            ),
        )


class EventScheduleModal(discord.ui.Modal, title="When is it? — Step 2 of 3"):
    local_start = discord.ui.TextInput(
        label="Local start date and time",
        placeholder="YYYY-MM-DD HH:MM",
        max_length=16,
    )

    def __init__(
        self,
        event_cog: Event,
        draft: EventDraft,
        local_start: str | None = None,
    ) -> None:
        super().__init__()
        self.event_cog = event_cog
        self.draft = draft
        if local_start is not None:
            self.local_start.default = local_start

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.draft.timezone is None:
            await interaction.response.send_message(
                "Choose a timezone before entering the start time.",
                ephemeral=True,
                view=EventTimezoneView(self.event_cog, self.draft),
            )
            return

        try:
            self.draft.scheduled_at = _parse_event_time(
                self.local_start.value.strip(),
                self.draft.timezone,
            )
        except ValueError as error:
            await self._retry(
                interaction,
                str(error),
            )
            return

        await interaction.response.send_message(
            "Schedule saved. Continue to configure group slots.",
            ephemeral=True,
            view=ContinueModalView(
                self.draft.creator_id,
                "Set group slots",
                lambda: EventSlotsModal(self.event_cog, self.draft),
            ),
        )

    async def _retry(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        await interaction.response.send_message(
            message,
            ephemeral=True,
            view=RetryModalView(
                self.draft.creator_id,
                lambda: EventScheduleModal(
                    self.event_cog,
                    self.draft,
                    self.local_start.value,
                ),
            ),
        )


class EventSlotsModal(discord.ui.Modal, title="Group setup — Step 3 of 3"):
    tank_slots = discord.ui.TextInput(
        label="Tank slots",
        placeholder="0",
        default="0",
        max_length=2,
    )
    healer_slots = discord.ui.TextInput(
        label="Healer slots",
        placeholder="0",
        default="0",
        max_length=2,
    )
    dps_slots = discord.ui.TextInput(
        label="DPS slots",
        placeholder="0",
        default="0",
        max_length=2,
    )
    min_job_level = discord.ui.TextInput(
        label="Minimum job level (1–100)",
        placeholder="1",
        default="1",
        max_length=3,
    )

    def __init__(
        self,
        event_cog: Event,
        draft: EventDraft,
        values: tuple[str, str, str, str] | None = None,
    ) -> None:
        super().__init__()
        self.event_cog = event_cog
        self.draft = draft
        if values is not None:
            for field, value in zip(
                (
                    self.tank_slots,
                    self.healer_slots,
                    self.dps_slots,
                    self.min_job_level,
                ),
                values,
            ):
                field.default = value

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = (
            self.tank_slots.value.strip(),
            self.healer_slots.value.strip(),
            self.dps_slots.value.strip(),
            self.min_job_level.value.strip(),
        )
        try:
            tank_slots, healer_slots, dps_slots, min_job_level = map(
                int,
                values,
            )
        except ValueError:
            await self._retry(
                interaction,
                "Enter whole numbers for each slot count and minimum level.",
                values,
            )
            return

        if any(slots < 0 for slots in (tank_slots, healer_slots, dps_slots)):
            await self._retry(
                interaction,
                "Role slot counts cannot be negative.",
                values,
            )
            return

        if tank_slots + healer_slots + dps_slots > 24:
            await self._retry(
                interaction,
                "An event cannot have more than 24 role slots.",
                values,
            )
            return

        if not 1 <= min_job_level <= 100:
            await self._retry(
                interaction,
                "Minimum job level must be between 1 and 100.",
                values,
            )
            return

        self.draft.tank_slots = tank_slots
        self.draft.healer_slots = healer_slots
        self.draft.dps_slots = dps_slots
        self.draft.min_job_level = min_job_level
        await interaction.response.send_message(
            self._summary(),
            ephemeral=True,
            view=EventConfirmationView(self.event_cog, self.draft),
        )

    def _summary(self) -> str:
        scheduled_at = self.draft.scheduled_at
        if scheduled_at is None:
            raise RuntimeError("The event schedule has not been set.")

        slots = (
            f"{self.draft.tank_slots} Tank, "
            f"{self.draft.healer_slots} Healer, "
            f"{self.draft.dps_slots} DPS"
        )
        description = (
            f"\n{self.draft.description}"
            if self.draft.description
            else ""
        )
        return (
            f"**Review your event**\n"
            f"**{self.draft.title}**\n"
            f"<t:{int(scheduled_at.timestamp())}:F>\n"
            f"Slots: {slots} "
            f"(minimum job level {self.draft.min_job_level})"
            f"{description}\n\n"
            "Create this event?"
        )

    async def _retry(
        self,
        interaction: discord.Interaction,
        message: str,
        values: tuple[str, str, str, str],
    ) -> None:
        await interaction.response.send_message(
            message,
            ephemeral=True,
            view=RetryModalView(
                self.draft.creator_id,
                lambda: EventSlotsModal(self.event_cog, self.draft, values),
            ),
        )


class EventConfirmationView(EventWizardView):
    def __init__(self, event_cog: Event, draft: EventDraft) -> None:
        super().__init__(draft.creator_id)
        self.event_cog = event_cog
        self.draft = draft

    @discord.ui.button(label="Create event", style=discord.ButtonStyle.success)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        database = getattr(self.event_cog.bot, "database", None)
        if database is None:
            await interaction.response.send_message(
                "The database is not available.",
                ephemeral=True,
            )
            return

        scheduled_at = self.draft.scheduled_at
        if scheduled_at is None:
            await interaction.response.send_message(
                "The event schedule is missing. Please start again.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        event_id = await database.create_event(
            guild_id=self.draft.guild_id,
            creator_id=self.draft.creator_id,
            title=self.draft.title,
            scheduled_at=scheduled_at,
            description=self.draft.description,
            tank_slots=self.draft.tank_slots,
            healer_slots=self.draft.healer_slots,
            dps_slots=self.draft.dps_slots,
            min_job_level=self.draft.min_job_level,
        )
        try:
            channel = self.event_cog.bot.get_channel(self.draft.channel_id)
            if channel is None:
                channel = await self.event_cog.bot.fetch_channel(
                    self.draft.channel_id
                )
            post = await channel.send(
                embed=await self.event_cog._make_event_embed_for_id(
                    event_id,
                ),
                view=EventPostView(self.event_cog, event_id),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            logger.warning(
                "Event %s was created but could not be posted to channel %s.",
                event_id,
                self.draft.channel_id,
                exc_info=error,
            )
            await interaction.followup.send(
                f"Created event **#{event_id} — {self.draft.title}**, but "
                "could not post it in this channel. Check the bot's channel "
                "permissions.",
                ephemeral=True,
            )
            return

        await database.set_event_post(
            event_id,
            self.draft.channel_id,
            post.id,
        )
        self.event_cog.bot.add_view(
            EventPostView(self.event_cog, event_id),
            message_id=post.id,
        )
        await interaction.edit_original_response(
            content=(
                f"Created event **#{event_id} — {self.draft.title}** "
                f"for <t:{int(scheduled_at.timestamp())}:F> and posted it "
                f"in <#{self.draft.channel_id}>."
            ),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content="Event creation cancelled.",
            view=None,
        )


class EventPostView(discord.ui.View):
    def __init__(self, event_cog: Event, event_id: int) -> None:
        super().__init__(timeout=None)
        self.event_cog = event_cog
        self.event_id = event_id

        details = discord.ui.Button(
            label="Details",
            style=discord.ButtonStyle.secondary,
            custom_id=f"xivbot:event:{event_id}:details",
        )
        details.callback = self._show_details
        self.add_item(details)

        join = discord.ui.Button(
            label="Join",
            style=discord.ButtonStyle.success,
            custom_id=f"xivbot:event:{event_id}:join",
        )
        join.callback = self._join
        self.add_item(join)

        leave = discord.ui.Button(
            label="Leave",
            style=discord.ButtonStyle.danger,
            custom_id=f"xivbot:event:{event_id}:leave",
        )
        leave.callback = self._leave
        self.add_item(leave)

    async def _show_details(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        event, embed = await self.event_cog._get_event_embed(
            self.event_id,
            interaction.guild_id,
        )
        if event is None:
            await interaction.followup.send(
                "That event could not be found in this server.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _join(self, interaction: discord.Interaction) -> None:
        await self.event_cog._open_signup(interaction, self.event_id)

    async def _leave(self, interaction: discord.Interaction) -> None:
        await self.event_cog._leave_event(interaction, self.event_id)


class EventSignupView(EventWizardView):
    def __init__(
        self,
        event_cog: Event,
        event_id: int,
        user_id: int,
        character: asyncpg.Record | dict[str, object],
        jobs: list[CharacterJob],
        role_options: list[discord.SelectOption],
        minimum_level: int,
    ) -> None:
        super().__init__(user_id)
        self.event_cog = event_cog
        self.event_id = event_id
        self.character = character
        self.jobs = jobs
        self.minimum_level = minimum_level

        self.role_select = discord.ui.Select(
            placeholder="Choose a role",
            min_values=1,
            max_values=1,
            options=role_options,
        )
        self.role_select.callback = self._selection_changed
        self.add_item(self.role_select)

        self.job_select = discord.ui.Select(
            placeholder="Choose a job",
            min_values=1,
            max_values=1,
            options=self._get_job_options(),
        )
        self.job_select.callback = self._selection_changed
        self.add_item(self.job_select)

        join = discord.ui.Button(
            label="Confirm signup",
            style=discord.ButtonStyle.success,
        )
        join.callback = self._submit_signup
        self.add_item(join)

    def _matches_role(self, job: CharacterJob, role: str) -> bool:
        if role == "DPS":
            return job.category in DPS_CATEGORIES
        return job.category == role

    def _get_job_options(self, role: str | None = None) -> list[discord.SelectOption]:
        filtered_jobs = [
            job
            for job in self.jobs
            if job.level is not None
            and job.level >= self.minimum_level
            and (role is None or self._matches_role(job, role))
        ]
        return [
            discord.SelectOption(
                label=f"{job.name} (Lv. {job.level})"[:100],
                value=job.name,
                description=job.category[:100],
            )
            for job in filtered_jobs
        ]

    async def _selection_changed(
        self,
        interaction: discord.Interaction,
    ) -> None:
        role = self.role_select.values[0] if self.role_select.values else None
        if role is not None:
            self.role_select.placeholder = f"Role: {role}"
        else:
            self.role_select.placeholder = "Choose a role"

        self.job_select.options = self._get_job_options(role)
        if self.job_select.values:
            selected_job = self.job_select.values[0]
            self.job_select.placeholder = f"Job: {selected_job}"
        elif role is not None and self.job_select.options:
            self.job_select.placeholder = "Choose a job"
        else:
            self.job_select.placeholder = "Choose a job"

        if not self.job_select.options:
            await interaction.response.send_message(
                "No jobs match that role at this event's minimum level requirement.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(view=self)

    async def _submit_signup(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.role_select.values or not self.job_select.values:
            await interaction.response.send_message(
                "Choose both a role and a job before signing up.",
                ephemeral=True,
            )
            return

        self.role_select.placeholder = f"Role: {self.role_select.values[0]}"
        self.job_select.placeholder = f"Job: {self.job_select.values[0]}"

        await self.event_cog._submit_signup(
            interaction,
            self.event_id,
            self.role_select.values[0],
            self.job_select.values[0],
            character=self.character,
            jobs=self.jobs,
        )


class Event(
    commands.GroupCog,
    group_name="event",
    group_description="Commands for creating and managing events.",
):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._expired_event_cleanup_task: asyncio.Task[None] | None = None
        self._event_reminder_task: asyncio.Task[None] | None = None

    async def cog_load(self) -> None:
        database = getattr(self.bot, "database", None)
        if database is None:
            return

        await self._prune_expired_events()
        await self._send_event_reminders()

        for event in await database.get_published_events():
            self.bot.add_view(
                EventPostView(self, event["event_id"]),
                message_id=event["post_message_id"],
            )

        if self._expired_event_cleanup_task is None or self._expired_event_cleanup_task.done():
            self._expired_event_cleanup_task = asyncio.create_task(
                self._expired_event_cleanup_loop()
            )
        if self._event_reminder_task is None or self._event_reminder_task.done():
            self._event_reminder_task = asyncio.create_task(
                self._event_reminder_loop()
            )

    def cog_unload(self) -> None:
        if self._expired_event_cleanup_task is not None:
            self._expired_event_cleanup_task.cancel()
            self._expired_event_cleanup_task = None
        if self._event_reminder_task is not None:
            self._event_reminder_task.cancel()
            self._event_reminder_task = None

    async def _expired_event_cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(3600)
                await self._prune_expired_events()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to prune expired events.")

    async def _event_reminder_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                await self._send_event_reminders()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to send event reminders.")

    async def _send_event_reminders(self) -> None:
        database = getattr(self.bot, "database", None)
        if database is None:
            return

        for reminder in await database.get_upcoming_event_reminders():
            event_id = reminder["event_id"]
            discord_user_id = reminder["discord_user_id"]
            title = str(reminder["title"])
            scheduled_at = reminder["scheduled_at"]
            if not isinstance(scheduled_at, datetime):
                continue

            try:
                user = self.bot.get_user(discord_user_id)
                if user is None:
                    user = await self.bot.fetch_user(discord_user_id)
                if user is None:
                    continue

                await user.send(
                    f"Reminder: your signup for **{title}** is coming up "
                    f"in about an hour on <t:{int(scheduled_at.timestamp())}:F>."
                )
                await database.mark_signup_reminder_sent(event_id, discord_user_id)
            except discord.HTTPException as error:
                logger.warning(
                    "Could not send event reminder for event %s to user %s.",
                    event_id,
                    discord_user_id,
                    exc_info=error,
                )
            except Exception:
                logger.exception(
                    "Unexpected error while sending reminder for event %s.",
                    event_id,
                )

    async def _prune_expired_events(self) -> None:
        database = getattr(self.bot, "database", None)
        if database is None:
            return

        expired_events = await database.get_expired_events(3.0)
        for event in expired_events:
            channel_id = event.get("post_channel_id")
            message_id = event.get("post_message_id")
            if channel_id is None or message_id is None:
                continue

            try:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    channel = await self.bot.fetch_channel(channel_id)
                message = await channel.fetch_message(message_id)
                await message.delete()
            except (discord.HTTPException, AttributeError, TypeError):
                logger.warning(
                    "Could not delete expired event post for event %s.",
                    event["event_id"],
                    exc_info=True,
                )

        await database.delete_expired_events(3.0)

    @staticmethod
    def _make_event_summary_embed(
        event: asyncpg.Record | dict[str, object],
        roles: list[asyncpg.Record] | list[dict[str, object]],
        signups: list[asyncpg.Record] | list[dict[str, object]],
    ) -> discord.Embed:
        scheduled_at = event["scheduled_at"]
        if not isinstance(scheduled_at, datetime):
            raise TypeError("Event schedule must be a datetime.")

        title = discord.utils.escape_markdown(str(event["title"]))
        embed = discord.Embed(
            title=f"Event #{event['event_id']} — {title}",
            description=(
                f"**Starts:** <t:{int(scheduled_at.timestamp())}:F>\n"
                f"**Minimum job level:** {event['min_job_level']}"
            ),
            color=discord.Color.blurple(),
        )

        description = event["description"]
        if description:
            embed.add_field(
                name="Description",
                value=discord.utils.escape_markdown(str(description))[:1024],
                inline=False,
            )

        role_lines = []
        for role in roles:
            role_name = str(role["role"])
            capacity = int(role["slots"])
            members = [
                signup
                for signup in signups
                if signup["role"] == role_name
            ]
            remaining = max(0, capacity - len(members))
            role_lines.append(
                f"{role_name}: {remaining} open / {capacity} total"
                if capacity
                else f"{role_name}: not recruiting"
            )

        if role_lines:
            embed.add_field(
                name="Slots",
                value="\n".join(role_lines),
                inline=False,
            )

        return embed

    @staticmethod
    def _make_event_details_embed(
        event: asyncpg.Record | dict[str, object],
        roles: list[asyncpg.Record] | list[dict[str, object]],
        signups: list[asyncpg.Record] | list[dict[str, object]],
    ) -> discord.Embed:
        scheduled_at = event["scheduled_at"]
        if not isinstance(scheduled_at, datetime):
            raise TypeError("Event schedule must be a datetime.")

        title = discord.utils.escape_markdown(str(event["title"]))
        embed = discord.Embed(
            title=f"Event #{event['event_id']} — {title}",
            description=(
                f"**Starts:** <t:{int(scheduled_at.timestamp())}:F>\n"
                f"**Minimum job level:** {event['min_job_level']}"
            ),
            color=discord.Color.blurple(),
        )
        description = event["description"]
        if description:
            embed.add_field(
                name="Details",
                value=discord.utils.escape_markdown(str(description))[:1024],
                inline=False,
            )

        for role in roles:
            role_name = str(role["role"])
            capacity = int(role["slots"])
            members = [
                signup
                for signup in signups
                if signup["role"] == role_name
            ]
            remaining = max(0, capacity - len(members))
            slot_label = "slot" if remaining == 1 else "slots"
            embed.add_field(
                name=f"{role_name} — {remaining} {slot_label} left",
                value=(
                    f"{len(members)}/{capacity} registered"
                    if capacity
                    else "Not recruiting"
                ),
                inline=True,
            )
            if not members:
                continue

            lines = [
                (
                    f"<@{signup['discord_user_id']}> — "
                    f"**{discord.utils.escape_markdown(str(signup['character_name']))}** "
                    f"@ {discord.utils.escape_markdown(str(signup['world']))}; "
                    f"{discord.utils.escape_markdown(str(signup['job']))} "
                    f"Lv. {signup['job_level']}"
                )
                for signup in members
            ]
            chunk: list[str] = []
            chunk_length = 0
            chunk_number = 1
            for line in lines:
                if chunk and chunk_length + len(line) + 1 > 950:
                    embed.add_field(
                        name=(
                            f"{role_name} signups"
                            if chunk_number == 1
                            else f"{role_name} signups (continued)"
                        ),
                        value="\n".join(chunk),
                        inline=False,
                    )
                    chunk = []
                    chunk_length = 0
                    chunk_number += 1
                chunk.append(line)
                chunk_length += len(line) + 1

            if chunk:
                embed.add_field(
                    name=(
                        f"{role_name} signups"
                        if chunk_number == 1
                        else f"{role_name} signups (continued)"
                    ),
                    value="\n".join(chunk),
                    inline=False,
                )

        return embed

    @staticmethod
    def _make_event_embed(
        event: asyncpg.Record | dict[str, object],
        roles: list[asyncpg.Record] | list[dict[str, object]],
        signups: list[asyncpg.Record] | list[dict[str, object]],
    ) -> discord.Embed:
        return Event._make_event_summary_embed(event, roles, signups)

    async def _get_event_embed(
        self,
        event_id: int,
        guild_id: int | None,
    ) -> tuple[asyncpg.Record | dict[str, object] | None, discord.Embed | None]:
        database = getattr(self.bot, "database", None)
        if database is None or guild_id is None:
            return None, None

        event = await database.get_event(event_id)
        if event is None or event["guild_id"] != guild_id:
            return None, None

        embed = self._make_event_details_embed(
            event,
            await database.get_event_roles(event_id),
            await database.get_event_signups(event_id),
        )
        return event, embed

    async def _make_event_embed_for_id(self, event_id: int) -> discord.Embed:
        database = getattr(self.bot, "database", None)
        if database is None:
            raise RuntimeError("The database is not available.")

        event = await database.get_event(event_id)
        if event is None:
            raise RuntimeError(f"Created event {event_id} could not be found.")

        return self._make_event_summary_embed(
            event,
            await database.get_event_roles(event_id),
            await database.get_event_signups(event_id),
        )

    async def _refresh_event_post(
        self,
        event_id: int,
        message: discord.Message | None = None,
    ) -> bool:
        database = getattr(self.bot, "database", None)
        if database is None:
            return False

        event = await database.get_event(event_id)
        if event is None:
            return False

        if message is None:
            try:
                channel_id = event["post_channel_id"]
                message_id = event["post_message_id"]
            except KeyError:
                return True
            if channel_id is None or message_id is None:
                return True

            try:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    channel = await self.bot.fetch_channel(channel_id)
                message = await channel.fetch_message(message_id)
            except discord.HTTPException as error:
                logger.warning(
                    "Could not retrieve the channel post for event %s.",
                    event_id,
                    exc_info=error,
                )
                return False

        try:
            await message.edit(
                embed=self._make_event_embed(
                    event,
                    await database.get_event_roles(event_id),
                    await database.get_event_signups(event_id),
                ),
                view=EventPostView(self, event_id),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            logger.warning(
                "Could not update event post for event %s.",
                event_id,
                exc_info=error,
            )
            return False
        return True

    async def _open_signup(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
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
        signups = await database.get_event_signups(event_id)
        current_signup = next(
            (
                signup
                for signup in signups
                if signup["discord_user_id"] == interaction.user.id
            ),
            None,
        )
        role_options = []
        for role in role_slots:
            role_name = role["role"]
            capacity = role["slots"]
            if capacity <= 0:
                continue
            registered = sum(
                signup["role"] == role_name
                for signup in signups
            )
            if current_signup is not None and current_signup["role"] == role_name:
                registered -= 1
            available = capacity - registered
            if available > 0:
                role_options.append(
                    discord.SelectOption(
                        label=f"{role_name} ({available} left)",
                        value=role_name,
                    )
                )

        if not role_options:
            await interaction.followup.send(
                "There are no open role slots for this event.",
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

        combat_categories = {"Tank", "Healer"} | DPS_CATEGORIES
        minimum_level = event["min_job_level"]
        leveled_jobs = [
            job
            for job in jobs
            if job.level is not None
            and job.level >= minimum_level
            and job.category in combat_categories
        ]
        if not leveled_jobs:
            await interaction.followup.send(
                "Your linked character has no combat jobs at level "
                f"{minimum_level} or higher.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "Choose a role and a job, then confirm your signup.",
            view=EventSignupView(
                self,
                event_id,
                interaction.user.id,
                character,
                leveled_jobs,
                role_options,
                minimum_level,
            ),
            ephemeral=True,
        )

    async def _submit_signup(
        self,
        interaction: discord.Interaction,
        event_id: int,
        role: str,
        job: str,
        *,
        character: asyncpg.Record | dict[str, object] | None = None,
        jobs: list[CharacterJob] | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
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
        if not any(
            entry["role"] == role and entry["slots"] > 0
            for entry in role_slots
        ):
            await interaction.followup.send(
                f"This event has no {role} slots.",
                ephemeral=True,
            )
            return

        signups = await database.get_event_signups(event_id)
        current_signup = next(
            (
                signup
                for signup in signups
                if signup["discord_user_id"] == interaction.user.id
            ),
            None,
        )
        role_capacity = next(
            (
                entry["slots"]
                for entry in role_slots
                if entry["role"] == role
            ),
            0,
        )
        registered_for_role = sum(
            signup["role"] == role
            for signup in signups
        )
        if current_signup is not None and current_signup["role"] == role:
            registered_for_role -= 1
        if role_capacity > 0 and registered_for_role >= role_capacity:
            await interaction.followup.send(
                f"All {role} slots for this event are full.",
                ephemeral=True,
            )
            return

        if character is None:
            character = await database.get_character_link(interaction.user.id)
        if character is None:
            await interaction.followup.send(
                "Link your FFXIV character first with `/character link`.",
                ephemeral=True,
            )
            return

        if jobs is None:
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
        if job_role != role:
            await interaction.followup.send(
                f"{selected_job.name} is a {job_role} job, not a {role} job.",
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
            role=role,
            job=selected_job.name,
            job_level=selected_job.level,
            character_name=character["character_name"],
            world=character["world"],
        )
        messages = {
            "joined": (
                f"Signed up **{character['character_name']}** "
                f"({selected_job.name}, Lv. {selected_job.level}) "
                f"for **{role}** in event **#{event_id}**."
            ),
            "event_missing": "That event could not be found.",
            "role_unavailable": f"This event has no {role} slots.",
            "full": f"All {role} slots for this event are full.",
        }
        message = messages[result]
        if result == "joined" and not await self._refresh_event_post(event_id):
            message += (
                " Your signup was saved, but the channel event post could "
                "not be refreshed."
            )
        await interaction.followup.send(message, ephemeral=True)

    async def _leave_event(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
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

        result: LeaveResult = await database.leave_event(
            event_id,
            interaction.user.id,
        )
        messages = {
            "left": f"You left event **#{event_id}**.",
            "not_signed_up": f"You are not signed up for event **#{event_id}**.",
            "event_missing": "That event could not be found.",
        }
        message = messages[result]
        if result == "left" and not await self._refresh_event_post(
            event_id,
            interaction.message,
        ):
            message += (
                " You left the event, but the channel event post could "
                "not be refreshed."
            )
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(
        name="create",
        description="Walk through creating a new event.",
    )
    async def create(
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

        if interaction.channel_id is None:
            await interaction.response.send_message(
                "I couldn't determine which channel to post the event in.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            EventDetailsModal(
                self,
                EventDraft(
                    guild_id=interaction.guild_id,
                    creator_id=interaction.user.id,
                    channel_id=interaction.channel_id,
                ),
            )
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
        await self._submit_signup(
            interaction,
            event_id,
            role.value,
            job,
        )

    @app_commands.command(
        name="leave",
        description="Leave an event you can no longer attend.",
    )
    @app_commands.describe(event_id="The event number.")
    async def leave(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        await self._leave_event(interaction, event_id)

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
        embed = self._make_event_embed(event, roles, signups)
        await interaction.response.send_message(
            embed=embed,
            ephemeral=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Event(bot))