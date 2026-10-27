from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from xivbot.cogs.event import Event
from xivbot.models.character import CharacterJob


@pytest.mark.asyncio
async def test_create_event_converts_local_time_and_uses_discord_timestamp() -> None:
    database = AsyncMock()
    database.create_event.return_value = 7
    bot = SimpleNamespace(database=database)
    event = Event(bot)
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await Event.create.callback(
        event,
        interaction,
        "Test event",
        "2026-10-30 20:00",
        "America/New_York",
    )

    expected_time = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
    database.create_event.assert_awaited_once_with(
        guild_id=123,
        creator_id=456,
        title="Test event",
        scheduled_at=expected_time,
        description=None,
        tank_slots=0,
        healer_slots=0,
        dps_slots=0,
        min_job_level=1,
    )
    interaction.response.send_message.assert_awaited_once_with(
        f"Created event **#7 — Test event** "
        f"for <t:{int(expected_time.timestamp())}:F>.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_create_event_saves_role_slots_and_minimum_level() -> None:
    database = AsyncMock()
    database.create_event.return_value = 8
    event = Event(SimpleNamespace(database=database))
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await Event.create.callback(
        event,
        interaction,
        "Savage",
        "2026-10-30 20:00",
        "America/New_York",
        tank_slots=2,
        healer_slots=2,
        dps_slots=4,
        min_job_level=90,
    )

    database.create_event.assert_awaited_once()
    assert database.create_event.await_args.kwargs["tank_slots"] == 2
    assert database.create_event.await_args.kwargs["healer_slots"] == 2
    assert database.create_event.await_args.kwargs["dps_slots"] == 4
    assert database.create_event.await_args.kwargs["min_job_level"] == 90
    assert "8 slots: 2 Tank, 2 Healer, 4 DPS" in (
        interaction.response.send_message.await_args.args[0]
    )


@pytest.mark.asyncio
async def test_create_event_rejects_unknown_timezone() -> None:
    database = AsyncMock()
    event = Event(SimpleNamespace(database=database))
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await Event.create.callback(
        event,
        interaction,
        "Test event",
        "2026-10-30 20:00",
        "Not/A_Timezone",
    )

    database.create_event.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        "Invalid timezone. Use an IANA timezone such as `America/New_York`.",
        ephemeral=True,
    )


@pytest.mark.parametrize(
    "scheduled_at",
    [
        "2026-03-08 02:30",
        "2026-11-01 01:30",
    ],
)
@pytest.mark.asyncio
async def test_create_event_rejects_invalid_daylight_saving_times(
    scheduled_at: str,
) -> None:
    database = AsyncMock()
    event = Event(SimpleNamespace(database=database))
    interaction = SimpleNamespace(
        guild_id=123,
        user=SimpleNamespace(id=456),
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await Event.create.callback(
        event,
        interaction,
        "Test event",
        scheduled_at,
        "America/New_York",
    )

    database.create_event.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        "This local time does not exist in that timezone. "
        "Choose a different local time."
        if scheduled_at == "2026-03-08 02:30"
        else "This local time is ambiguous in that timezone. "
        "Choose a different local time.",
        ephemeral=True,
    )


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
