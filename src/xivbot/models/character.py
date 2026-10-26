from dataclasses import dataclass

# Converting Lodestone character search results into a dataclass for easier handling and manipulation of the data. This allows for better organization and access to the character's information, such as their ID, name, world, data center, and profile URL.
@dataclass(frozen=True)
class CharacterSearchResult:
    lodestone_id: int
    name: str
    world: str
    data_center: str
    profile_url: str