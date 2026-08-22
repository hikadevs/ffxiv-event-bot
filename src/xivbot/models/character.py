from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterSearchResult:
    lodestone_id: int
    name: str
    world: str
    data_center: str
    profile_url: str