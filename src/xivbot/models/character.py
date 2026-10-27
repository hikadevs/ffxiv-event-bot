from dataclasses import dataclass

# Represents a character returned by the Lodestone search page.
@dataclass(frozen=True)
class CharacterSearchResult:
    lodestone_id: int
    name: str
    world: str
    data_center: str
    profile_url: str


# Represents detailed information from an individual Lodestone character page.
@dataclass(frozen=True)
class CharacterProfile:
    lodestone_id: int
    name: str
    world: str
    data_center: str
    race: str
    clan: str
    gender: str
    nameday: str
    guardian: str
    city_state: str | None
    grand_company: str | None
    portrait_url: str | None