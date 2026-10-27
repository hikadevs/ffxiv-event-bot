from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import aiohttp
from xivbot.services.lodestone import LodestoneClient, LodestoneError


def test_parse_world() -> None:
    world, data_center = LodestoneClient._parse_world(
        "Gilgamesh [Aether]"
    )

    assert world == "Gilgamesh"
    assert data_center == "Aether"


def test_parse_world_without_data_center() -> None:
    world, data_center = LodestoneClient._parse_world(
        "Gilgamesh"
    )

    assert world == "Gilgamesh"
    assert data_center == "Unknown"

def test_parse_search_results() -> None:
    html = """
    <div class="entry">
        <a href="/lodestone/character/12345678/">
            <p class="entry__name">Test Character</p>
            <p class="entry__world">Gilgamesh [Aether]</p>
        </a>
    </div>
    """

    client = LodestoneClient(Mock())

    results = client._parse_search_results(html)

    assert len(results) == 1

    character = results[0]

    assert character.lodestone_id == 12345678
    assert character.name == "Test Character"
    assert character.world == "Gilgamesh"
    assert character.data_center == "Aether"
    assert character.profile_url == (
        "https://na.finalfantasyxiv.com/lodestone/character/12345678/"
    )

def test_parse_search_results_with_no_entries() -> None:
    client = LodestoneClient(Mock())

    results = client._parse_search_results("<html></html>")

    assert results == []

def test_parse_search_results_multiple_characters() -> None:
    html = """
    <div class="entry">
        <a href="/lodestone/character/11111111/">
            <p class="entry__name">Alpha Character</p>
            <p class="entry__world">Gilgamesh [Aether]</p>
        </a>
    </div>

    <div class="entry">
        <a href="/lodestone/character/22222222/">
            <p class="entry__name">Beta Character</p>
            <p class="entry__world">Cactuar [Aether]</p>
        </a>
    </div>
    """

    client = LodestoneClient(Mock())

    results = client._parse_search_results(html)

    assert len(results) == 2

    assert results[0].name == "Alpha Character"
    assert results[0].world == "Gilgamesh"

    assert results[1].name == "Beta Character"
    assert results[1].world == "Cactuar"

@pytest.mark.asyncio
async def test_search_character_success() -> None:
    html = """
    <div class="entry">
        <a href="/lodestone/character/12345678/">
            <p class="entry__name">Test Character</p>
            <p class="entry__world">Gilgamesh [Aether]</p>
        </a>
    </div>
    """

    response = Mock()
    response.status = 200
    response.text = AsyncMock(return_value=html)

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    session = Mock()
    session.get.return_value = context_manager

    client = LodestoneClient(session)

    results = await client.search_character("Test Character")

    assert len(results) == 1
    assert results[0].name == "Test Character"
    assert results[0].world == "Gilgamesh"
    assert results[0].data_center == "Aether"

@pytest.mark.asyncio
async def test_search_character_raises_on_http_error() -> None:
    response = Mock()
    response.status = 500

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    session = Mock()
    session.get.return_value = context_manager

    client = LodestoneClient(session)

    with pytest.raises(LodestoneError):
        await client.search_character("Test Character")

@pytest.mark.asyncio
async def test_search_character_raises_on_network_error() -> None:
    session = Mock()
    session.get.side_effect = aiohttp.ClientError("Connection failed")

    client = LodestoneClient(session)

    with pytest.raises(LodestoneError):
        await client.search_character("Test Character")

def test_parse_character_jobs() -> None:
    html = """
    <div class="character__job">
        <p class="character__job__name">Paladin</p>
        <p class="character__job__level">100</p>
    </div>
    <div class="character__job">
        <p class="character__job__name">Unknown Level Job</p>
        <p class="character__job__level">--</p>
    </div>
    <div class="character__job">
        <p class="character__job__name">Incomplete Job</p>
    </div>
    """

    client = LodestoneClient(Mock())

    jobs = client._parse_character_jobs(html)

    assert len(jobs) == 2
    assert jobs[0].name == "Paladin"
    assert jobs[0].level == 100
    assert jobs[0].category == "Tank"
    assert jobs[1].name == "Unknown Level Job"
    assert jobs[1].level is None
    assert jobs[1].category == "Unknown"


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("White Mage", "Healer"),
        ("Dragoon", "Melee DPS"),
        ("Bard", "Physical Ranged DPS"),
        ("Black Mage", "Magical Ranged DPS"),
        ("Blue Mage", "Limited Job"),
        ("Carpenter", "Crafter"),
        ("Miner", "Gatherer"),
        ("Unknown Job", "Unknown"),
    ],
)
def test_get_job_category(name: str, category: str) -> None:
    assert LodestoneClient._get_job_category(name) == category


def test_parse_character_profile() -> None:
    html = """
    <html>
        <body>
            <p class="frame__chara__name">Hikaru Kiryuu</p>
            <p class="frame__chara__world">Zalera [Crystal]</p>

            <div class="character__detail__image">
                <img src="https://example.com/hikaru.jpg">
            </div>
        <div class="character-block__box">
            <p class="character-block__title">Race/Clan/Gender</p>
    <p class="character-block__name">
        Au Ra<br>
        Raen / ♀
    </p>
</div>
<div class="character-block__box">
    <p class="character-block__title">Nameday</p>
    <p class="character-block__birth">
        15th Sun of the 3rd Umbral Moon
    </p>

    <p class="character-block__title">Guardian</p>
    <p class="character-block__name">
        Llymlaen, the Navigator
    </p>
</div>
    <div class="character-block__box">
    <p class="character-block__title">City-state</p>
    <p class="character-block__name">
        Gridania
    </p>
</div>

<div class="character-block__box">
    <p class="character-block__title">Grand Company</p>
    <p class="character-block__name">
        Order of the Twin Adder / Serpent Captain
    </p>
</div>
        </body>
    </html>
    """

    client = LodestoneClient(Mock())

    profile = client._parse_character_profile(
        12345678,
        html,
    )

    assert profile.lodestone_id == 12345678
    assert profile.name == "Hikaru Kiryuu"
    assert profile.world == "Zalera"
    assert profile.data_center == "Crystal"
    assert profile.portrait_url == "https://example.com/hikaru.jpg"

    assert profile.race == "Au Ra"
    assert profile.clan == "Raen"
    assert profile.gender == "Female"
    assert profile.nameday == "15th Sun of the 3rd Umbral Moon"
    assert profile.guardian == "Llymlaen, the Navigator"
    assert profile.city_state == "Gridania"
    assert profile.grand_company == "Order of the Twin Adder / Serpent Captain"

@pytest.mark.asyncio
async def test_get_character_profile() -> None:
    html = """
    <html>
        <body>
            <p class="frame__chara__name">Hikaru Kiryuu</p>
            <p class="frame__chara__world">Zalera [Crystal]</p>

            <div class="character__detail__image">
                <img src="https://example.com/hikaru.jpg">
            </div>
        </body>
    </html>
    """

    response = MagicMock()
    response.status = 200
    response.text = AsyncMock(return_value=html)

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    session = Mock()
    session.get.return_value = context_manager

    client = LodestoneClient(session)

    profile = await client.get_character_profile(12345678)

    assert profile.lodestone_id == 12345678
    assert profile.name == "Hikaru Kiryuu"
    assert profile.world == "Zalera"
    assert profile.data_center == "Crystal"
    assert profile.portrait_url == "https://example.com/hikaru.jpg"

def test_parse_character_jobs() -> None:
    html = """
    <html>
        <body>
            <div class="character__job">
                <p class="character__job__name">Dark Knight</p>
                <p class="character__job__level">100</p>
            </div>

            <div class="character__job">
                <p class="character__job__name">Paladin</p>
                <p class="character__job__level">-</p>
            </div>
        </body>
    </html>
    """

    client = LodestoneClient(Mock())

    jobs = client._parse_character_jobs(html)

    assert len(jobs) == 2

    assert jobs[0].name == "Dark Knight"
    assert jobs[0].level == 100
    assert jobs[0].category == "Tank"

    assert jobs[1].name == "Paladin"
    assert jobs[1].level is None
    assert jobs[1].category == "Tank"

@pytest.mark.asyncio
async def test_get_character_jobs() -> None:
    html = """
    <html>
        <body>
            <ul class="character__job">
                <li>
                    <div class="character__job__name">Dark Knight</div>
                    <div class="character__job__level">100</div>
                </li>

                <li>
                    <div class="character__job__name">Paladin</div>
                    <div class="character__job__level">-</div>
                </li>
            </ul>
        </body>
    </html>
    """

    response = MagicMock()
    response.status = 200
    response.text = AsyncMock(return_value=html)

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    session = Mock()
    session.get.return_value = context_manager

    client = LodestoneClient(session)

    jobs = await client.get_character_jobs(12345678)

    assert len(jobs) == 2

    assert jobs[0].name == "Dark Knight"
    assert jobs[0].level == 100

    assert jobs[1].name == "Paladin"
    assert jobs[1].level is None