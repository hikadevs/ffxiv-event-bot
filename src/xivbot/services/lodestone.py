import re
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup

from xivbot.models.character import (
    CharacterJob,
    CharacterProfile,
    CharacterSearchResult,
)



class LodestoneError(Exception):
    """Base class for all Lodestone-related errors."""

# Client is an object responsible for communicating with external services.

class LodestoneClient:
    BASE_URL = "https://na.finalfantasyxiv.com"

    # Avoiding application creating brand new HTTP client each request, instead reusing existing client session for better performance and resource management.

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def search_character(
        self,
        name: str,
    ) -> list[CharacterSearchResult]:
        query = urlencode(
            {
                "q": name,
                "search_type": "character",
            }
        )

        url = f"{self.BASE_URL}/lodestone/character/?{query}"

        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise LodestoneError(
                        f"Lodestone returned HTTP {response.status} "
                        f"for search query '{name}'."
                    )

                html = await response.text()

        except aiohttp.ClientError as exc:
            raise LodestoneError(
                f"Failed to connect to Lodestone for search query '{name}'."
            ) from exc

        return self._parse_search_results(html)

    async def get_character_profile(
        self,
        lodestone_id: int,
    ) -> CharacterProfile:
        url = f"{self.BASE_URL}/lodestone/character/{lodestone_id}/"

        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise LodestoneError(
                        f"Lodestone returned HTTP {response.status} "
                        f"for character {lodestone_id}."
                    )

                html = await response.text()

        except aiohttp.ClientError as exc:
            raise LodestoneError(
                f"Failed to connect to Lodestone for character {lodestone_id}."
            ) from exc

        return self._parse_character_profile(
            lodestone_id,
            html,
        )

    async def get_character_jobs(
        self,
        lodestone_id: int,
    ) -> list[CharacterJob]:
        url = (
            f"{self.BASE_URL}/lodestone/character/"
            f"{lodestone_id}/class_job/"
        )

        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise LodestoneError(
                        f"Lodestone returned HTTP {response.status} "
                        f"for character jobs {lodestone_id}."
                    )

                html = await response.text()

        except aiohttp.ClientError as exc:
            raise LodestoneError(
                f"Failed to connect to Lodestone for "
                f"character jobs {lodestone_id}."
            ) from exc

        return self._parse_character_jobs(html)


    def _parse_search_results(
        self,
        html: str,
    ) -> list[CharacterSearchResult]:

# Turning raw HTML content into a BeautifulSoup object for easier parsing and extraction of relevant data. The "html.parser" is used to parse the HTML content.
        soup = BeautifulSoup(html, "html.parser")

        results: list[CharacterSearchResult] = []

        for entry in soup.select(".entry"):
            link = entry.select_one("a[href^='/lodestone/character/']")

            if link is None:
                continue

            href = link.get("href")

            if not isinstance(href, str):
                continue

# Capturing the Lodestone character ID from the href attribute of the link using a regular expression. The character ID is extracted from the URL and converted to an integer for further processing. \d+ means capturing more than 1 digit
            match = re.search(
                r"/lodestone/character/(\d+)",
                href,
            )

            if match is None:
                continue
# turns text captured by the regex into an integer to be stored in the CharacterSearchResult dataclass.
            lodestone_id = int(match.group(1))

            name_element = entry.select_one(
                ".entry__name"
                )

            world_element = entry.select_one(
                ".entry__world"

            )

            if name_element is None or world_element is None:
                continue

            character_name = name_element.get_text(
                " ",
                strip=True
                )
            world_text = world_element.get_text(
                " ",
                strip=True,
            )
# Parsing the world and data center information from the world_text using a helper method. The _parse_world method extracts the world name and data center from the text and returns them as a tuple.
            world, data_center = self._parse_world(world_text)

            results.append(
                CharacterSearchResult(
                    lodestone_id=lodestone_id,
                    name=character_name,
                    world=world,
                    data_center=data_center,
                    profile_url=f"{self.BASE_URL}{href}",
                )
            )
        return results

    def _parse_character_profile(
        self,
        lodestone_id: int,
        html: str,
    ) -> CharacterProfile:
        soup = BeautifulSoup(html, "html.parser")

        # Character name and home world
        name_element = soup.select_one(".frame__chara__name")
        world_element = soup.select_one(".frame__chara__world")

        if name_element is None or world_element is None:
            raise LodestoneError(
                f"Could not parse character profile {lodestone_id}."
            )

        name = name_element.get_text(
            " ",
            strip=True,
        )

        world_text = world_element.get_text(
            " ",
            strip=True,
        )

        world, data_center = self._parse_world(world_text)

        # Character portrait
        portrait_element = soup.select_one(
            ".character__detail__image img"
        )

        portrait_url: str | None = None

        if portrait_element is not None:
            src = portrait_element.get("src")

            if isinstance(src, str):
                portrait_url = src

        # Default values in case Lodestone does not provide a field
        race = "Unknown"
        clan = "Unknown"
        gender = "Unknown"
        nameday = "Unknown"
        guardian = "Unknown"
        city_state: str | None = None
        grand_company: str | None = None

        # Look through the profile information blocks
        for block in soup.select(".character-block__box"):
            titles = block.select(".character-block__title")

            for title in titles:
                label = title.get_text(
                    " ",
                    strip=True,
                )

                if label == "Race/Clan/Gender":
                    value = block.select_one(
                        ".character-block__name"
                    )

                    if value is not None:
                        parts = list(value.stripped_strings)

                        if len(parts) >= 2:
                            race = parts[0]

                            clan_gender = parts[1].rsplit(
                                " / ",
                                1,
                            )

                            clan = clan_gender[0]

                            if len(clan_gender) == 2:
                                gender_symbol = clan_gender[1]

                                if gender_symbol == "♀":
                                    gender = "Female"
                                elif gender_symbol == "♂":
                                    gender = "Male"
                                else:
                                    gender = gender_symbol

                elif label == "Nameday":
                    value = title.find_next_sibling(
                        class_="character-block__birth"
                    )

                    if value is not None:
                        nameday = value.get_text(
                            " ",
                            strip=True,
                        )

                elif label == "Guardian":
                    value = title.find_next_sibling(
                        class_="character-block__name"
                    )

                    if value is not None:
                        guardian = value.get_text(
                            " ",
                            strip=True,
                        )

                elif label == "City-state":
                    value = title.find_next_sibling(
                        class_="character-block__name"
                    )

                    if value is not None:
                        city_state = value.get_text(
                            " ",
                            strip=True,
                        )

                elif label == "Grand Company":
                    value = title.find_next_sibling(
                        class_="character-block__name"
                    )

                    if value is not None:
                        grand_company = value.get_text(
                            " ",
                            strip=True,
                        )

        return CharacterProfile(
            lodestone_id=lodestone_id,
            name=name,
            world=world,
            data_center=data_center,
            race=race,
            clan=clan,
            gender=gender,
            nameday=nameday,
            guardian=guardian,
            city_state=city_state,
            grand_company=grand_company,
            portrait_url=portrait_url,
        )

    def _parse_character_jobs(
        self,
        html: str,
    ) -> list[CharacterJob]:
        soup = BeautifulSoup(html, "html.parser")

        jobs: list[CharacterJob] = []

        items = soup.select(".character__job li")

        if not items:
            items = soup.select(".character__job")

        for item in items:
            name_element = item.select_one(
                ".character__job__name"
            )

            level_element = item.select_one(
                ".character__job__level"
            )

            if name_element is None or level_element is None:
                continue

            name = name_element.get_text(
                " ",
                strip=True,
            )

            level_text = level_element.get_text(
                " ",
                strip=True,
            )

            level: int | None = None

            if level_text.isdigit():
                level = int(level_text)

            jobs.append(
                CharacterJob(
                    name=name,
                    level=level,
                    category=self._get_job_category(name),
                )
            )

        return jobs

    @staticmethod
    def _get_job_category(name: str) -> str:
        tanks = {
            "Gladiator",
            "Paladin",
            "Marauder",
            "Warrior",
            "Dark Knight",
            "Gunbreaker",
        }

        healers = {
            "Conjurer",
            "White Mage",
            "Scholar",
            "Astrologian",
            "Sage",
        }

        melee_dps = {
            "Pugilist",
            "Monk",
            "Lancer",
            "Dragoon",
            "Rogue",
            "Ninja",
            "Samurai",
            "Reaper",
            "Viper",
        }

        physical_ranged_dps = {
            "Archer",
            "Bard",
            "Machinist",
            "Dancer",
        }

        magical_ranged_dps = {
            "Thaumaturge",
            "Black Mage",
            "Arcanist",
            "Summoner",
            "Red Mage",
            "Pictomancer",
        }

        limited_jobs = {
            "Blue Mage",
            "Beastmaster",
        }

        crafters = {
            "Carpenter",
            "Blacksmith",
            "Armorer",
            "Goldsmith",
            "Leatherworker",
            "Weaver",
            "Alchemist",
            "Culinarian",
        }

        gatherers = {
            "Miner",
            "Botanist",
            "Fisher",
        }

        if name in tanks:
            return "Tank"

        if name in healers:
            return "Healer"

        if name in melee_dps:
            return "Melee DPS"

        if name in physical_ranged_dps:
            return "Physical Ranged DPS"

        if name in magical_ranged_dps:
            return "Magical Ranged DPS"

        if name in limited_jobs:
            return "Limited Job"

        if name in crafters:
            return "Crafter"

        if name in gatherers:
            return "Gatherer"

        return "Unknown"

    @staticmethod
    def _parse_world(world_text: str) -> tuple[str, str]:
        match = re.match(
            r"(.+?)\s+\[(.+?)\]",
            world_text,
        )

        if match is None:
            return world_text, "Unknown"

        return (
            match.group(1).strip(),
            match.group(2).strip()
        )