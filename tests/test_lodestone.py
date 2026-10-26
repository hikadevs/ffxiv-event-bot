from xivbot.services.lodestone import LodestoneClient
from unittest.mock import Mock

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