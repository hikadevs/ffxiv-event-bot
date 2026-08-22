import re
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup

from xivbot.models.character import CharacterSearchResult



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

 # Builds the URL for the Lodestone character search query using the provided name and encodes it as a query string. The search_type parameter is set to "character" to specify that we are searching for characters.      
        query = urlencode(
            {
                "q": name,
                "search_type": "character",
                }
            )

        url = f"{self.BASE_URL}/lodestone/character/?{query}"

        try:

# checks the response status code to ensure that the request was successful (HTTP 200 OK). If the status code is not 200, it raises a LodestoneError with a message indicating the failure. It then reads the response content as text for further processing.
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise LodestoneError(
                        f"Lodestone returned HTTP {response.status} for search query '{name}'."
                    )

                html = await response.text()

        except aiohttp.ClientError as exc:
            raise LodestoneError(
                f"Failed to connect to Lodestone for search query '{name}'."
            ) from exc

        return self._parse_search_results(html)


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