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