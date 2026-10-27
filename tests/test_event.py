from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from xivbot.cogs.event import (
    Event,
    EventConfirmationView,
    EventDetailsModal,
    EventDraft,
    EventPostView,
    EventSignupView,
    EventScheduleModal,
    EventSlotsModal,
    RetryModalView,
    _parse_event_time,
)
from xivbot.models.character import CharacterJob


@pytest.mark.asyncio
async def test_create_event_starts_walkthrough() -> None:
    database = AsyncMock()
    event = Event(SimpleNamespace(database=database))
    interaction = SimpleNamespace(
        guild_id=123,
        channel_id=789,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(send_modal=AsyncMock()),
    )

    await Event.create.callback(event, interaction)

    modal = interaction.response.send_modal.await_args.args[0]
    assert isinstance(modal, EventDetailsModal)
    assert modal.draft.guild_id == 123
    assert modal.draft.creator_id == 456
    assert modal.draft.channel_id == 789
    database.create_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_creation_walkthrough_collects_draft_and_requests_confirmation() -> None:
    database = AsyncMock()
    event = Event(SimpleNamespace(database=database))
    draft = EventDraft(guild_id=123, creator_id=456, channel_id=789)
    details = EventDetailsModal(event, draft)
    details.event_title._value = "Savage"
    details.event_description._value = "Bring food"
    details_interaction = SimpleNamespace(
        response=SimpleNamespace(send_modal=AsyncMock()),
    )

    await details.on_submit(details_interaction)
    schedule = details_interaction.response.send_modal.await_args.args[0]
    assert isinstance(schedule, EventScheduleModal)
    assert draft.title == "Savage"
    assert draft.description == "Bring food"

    schedule.local_start._value = "2026-10-30 20:00"
    schedule.timezone._value = "America/New_York"
    schedule_interaction = SimpleNamespace(
        response=SimpleNamespace(send_modal=AsyncMock()),
    )
    await schedule.on_submit(schedule_interaction)
    slots = schedule_interaction.response.send_modal.await_args.args[0]
    assert isinstance(slots, EventSlotsModal)
    assert draft.scheduled_at == datetime(
        2026,
        10,
        31,
        0,
        0,
        tzinfo=timezone.utc,
    )

    slots.tank_slots._value = "2"
    slots.healer_slots._value = "2"
    slots.dps_slots._value = "4"
    slots.min_job_level._value = "90"
    slots_interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock()),
    )
    await slots.on_submit(slots_interaction)
    summary, = slots_interaction.response.send_message.await_args.args
    view = slots_interaction.response.send_message.await_args.kwargs["view"]
    assert "2 Tank, 2 Healer, 4 DPS" in summary
    assert "minimum job level 90" in summary
    assert isinstance(view, EventConfirmationView)
    assert draft.tank_slots == 2
    assert draft.healer_slots == 2
    assert draft.dps_slots == 4
    assert draft.min_job_level == 90
    database.create_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_creation_can_retry_a_blank_name() -> None:
    event = Event(SimpleNamespace(database=AsyncMock()))
    details = EventDetailsModal(
        event,
        EventDraft(guild_id=123, creator_id=456, channel_id=789),
    )
    details.event_title._value = "   "
    details.event_description._value = ""
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await details.on_submit(interaction)

    assert interaction.response.send_message.await_args.args == (
        "Enter a name for the event.",
    )
    assert isinstance(
        interaction.response.send_message.await_args.kwargs["view"],
        RetryModalView,
    )


@pytest.mark.asyncio
async def test_confirmation_creates_event_after_review() -> None:
    database = AsyncMock()
    database.create_event.return_value = 7
    channel = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=987)))
    bot = SimpleNamespace(
        database=database,
        get_channel=Mock(return_value=channel),
        add_view=Mock(),
    )
    event = Event(bot)
    scheduled_at = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
    draft = EventDraft(
        guild_id=123,
        creator_id=456,
        channel_id=789,
        title="Savage",
        description="Bring food",
        scheduled_at=scheduled_at,
        tank_slots=2,
        healer_slots=2,
        dps_slots=4,
        min_job_level=90,
    )
    view = EventConfirmationView(event, draft)
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    event._make_event_embed_for_id = AsyncMock(return_value=object())

    create_button = view.children[0]
    await create_button.callback(interaction)

    database.create_event.assert_awaited_once_with(
        guild_id=123,
        creator_id=456,
        title="Savage",
        scheduled_at=scheduled_at,
        description="Bring food",
        tank_slots=2,
        healer_slots=2,
        dps_slots=4,
        min_job_level=90,
    )
    channel.send.assert_awaited_once()
    database.set_event_post.assert_awaited_once_with(7, 789, 987)
    bot.add_view.assert_called_once()
    interaction.edit_original_response.assert_awaited_once_with(
        content=(
            f"Created event **#7 — Savage** "
            f"for <t:{int(scheduled_at.timestamp())}:F> and posted it "
            "in <#789>."
        ),
        view=None,
    )


def test_parse_event_time_converts_local_time_to_utc() -> None:
    event_time = _parse_event_time("2026-10-30 20:00", "America/New_York")

    assert event_time == datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)


def test_parse_event_time_rejects_unknown_timezone() -> None:
    with pytest.raises(ValueError, match="Invalid timezone"):
        _parse_event_time("2026-10-30 20:00", "Not/A_Timezone")


@pytest.mark.parametrize(
    "scheduled_at",
    [
        "2026-03-08 02:30",
        "2026-11-01 01:30",
    ],
)
def test_parse_event_time_rejects_invalid_daylight_saving_times(
    scheduled_at: str,
) -> None:
    expected_error = (
        "does not exist"
        if scheduled_at == "2026-03-08 02:30"
        else "ambiguous"
    )
    with pytest.raises(ValueError, match=expected_error):
        _parse_event_time(scheduled_at, "America/New_York")


def test_event_post_embed_shows_roster_and_remaining_slots() -> None:
    embed = Event._make_event_embed(
        {
            "event_id": 7,
            "title": "Savage",
            "scheduled_at": datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc),
            "description": "Bring food",
            "min_job_level": 90,
        },
        [
            {"role": "Tank", "slots": 2},
            {"role": "Healer", "slots": 1},
            {"role": "DPS", "slots": 0},
        ],
        [
            {
                "discord_user_id": 456,
                "role": "Tank",
                "job": "Paladin",
                "job_level": 100,
                "character_name": "Test Character",
                "world": "Gilgamesh",
            },
        ],
    )

    fields = {field.name: field.value for field in embed.fields}
    assert embed.title == "Event #7 — Savage"
    assert "Bring food" in fields["Details"]
    assert "1/2 registered" in fields["Tank — 1 slot left"]
    assert "<@456>" in fields["Tank signups"]
    assert "Test Character" in fields["Tank signups"]
    assert "Paladin Lv. 100" in fields["Tank signups"]
    assert "0/1 registered" in fields["Healer — 1 slot left"]
    assert "Not recruiting" in fields["DPS — 0 slots left"]


def test_event_post_controls_have_persistent_event_specific_ids() -> None:
    view = EventPostView(Event(SimpleNamespace(database=AsyncMock())), 42)

    assert view.timeout is None
    assert [button.custom_id for button in view.children] == [
        "xivbot:event:42:details",
        "xivbot:event:42:join",
        "xivbot:event:42:leave",
    ]


@pytest.mark.asyncio
async def test_event_join_button_offers_available_roles_and_combat_jobs() -> None:
    database = AsyncMock()
    database.get_event.return_value = {
        "guild_id": 123,
        "min_job_level": 90,
    }
    database.get_event_roles.return_value = [
        {"role": "Tank", "slots": 2},
        {"role": "Healer", "slots": 0},
        {"role": "DPS", "slots": 1},
    ]
    database.get_event_signups.return_value = []
    database.get_character_link.return_value = {
        "lodestone_id": 789,
        "character_name": "Test Character",
        "world": "Gilgamesh",
    }
    event = Event(
        SimpleNamespace(database=database, html_session=object())
    )
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    jobs = [
        CharacterJob("Paladin", 100, "Tank"),
        CharacterJob("Black Mage", 100, "Magical Ranged DPS"),
        CharacterJob("Carpenter", 100, "Crafter"),
        CharacterJob("White Mage", 80, "Healer"),
    ]

    with patch(
        "xivbot.cogs.event.LodestoneClient.get_character_jobs",
        new=AsyncMock(return_value=jobs),
    ):
        await event._open_signup(interaction, 7)

    view = interaction.followup.send.await_args.kwargs["view"]
    assert isinstance(view, EventSignupView)
    assert [option.value for option in view.role_select.options] == [
        "Tank",
        "DPS",
    ]
    assert [option.value for option in view.job_select.options] == [
        "Paladin",
        "Black Mage",
    ]


@pytest.mark.asyncio
async def test_join_event_validates_job_role_and_level() -> None:
    database = AsyncMock()
    database.get_event.return_value = {
        "guild_id": 123,
        "min_job_level": 90,
    }
    database.get_event_roles.return_value = [
        {"role": "Tank", "slots": 2},
        {"role": "Healer", "slots": 2},
        {"role": "DPS", "slots": 4},
    ]
    database.get_character_link.return_value = {
        "lodestone_id": 789,
        "character_name": "Test Character",
        "world": "Gilgamesh",
    }
    database.join_event.return_value = "joined"
    bot = SimpleNamespace(
        database=database,
        html_session=object(),
    )
    event = Event(bot)
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    dps_role = SimpleNamespace(value="DPS")

    with patch(
        "xivbot.cogs.event.LodestoneClient.get_character_jobs",
        new=AsyncMock(
            return_value=[
                CharacterJob("Black Mage", 100, "Magical Ranged DPS"),
            ],
        ),
    ):
        await Event.join.callback(
            event,
            interaction,
            7,
            dps_role,
            "Black Mage",
        )

    database.join_event.assert_awaited_once_with(
        event_id=7,
        discord_user_id=456,
        role="DPS",
        job="Black Mage",
        job_level=100,
        character_name="Test Character",
        world="Gilgamesh",
    )
    interaction.followup.send.assert_awaited_once_with(
        "Signed up **Test Character** (Black Mage, Lv. 100) "
        "for **DPS** in event **#7**.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_join_event_rejects_job_below_minimum_level() -> None:
    database = AsyncMock()
    database.get_event.return_value = {
        "guild_id": 123,
        "min_job_level": 90,
    }
    database.get_event_roles.return_value = [
        {"role": "Tank", "slots": 2},
    ]
    database.get_character_link.return_value = {
        "lodestone_id": 789,
        "character_name": "Test Character",
        "world": "Gilgamesh",
    }
    event = Event(
        SimpleNamespace(database=database, html_session=object())
    )
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    with patch(
        "xivbot.cogs.event.LodestoneClient.get_character_jobs",
        new=AsyncMock(
            return_value=[CharacterJob("Paladin", 80, "Tank")],
        ),
    ):
        await Event.join.callback(
            event,
            interaction,
            7,
            SimpleNamespace(value="Tank"),
            "Paladin",
        )

    database.join_event.assert_not_awaited()
    interaction.followup.send.assert_awaited_once_with(
        "Paladin is level 80; this event requires level 90 or higher.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_leave_event_removes_signup_and_refreshes_channel_post() -> None:
    database = AsyncMock()
    database.get_event.return_value = {"guild_id": 123}
    database.leave_event.return_value = "left"
    event = Event(SimpleNamespace(database=database))
    event._refresh_event_post = AsyncMock(return_value=True)
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        message=object(),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await event._leave_event(interaction, 7)

    database.leave_event.assert_awaited_once_with(7, 456)
    event._refresh_event_post.assert_awaited_once_with(7, interaction.message)
    interaction.followup.send.assert_awaited_once_with(
        "You left event **#7**.",
        ephemeral=True,
    )
