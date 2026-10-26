import asyncpg


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            dsn=self.database_url,
            min_size=1,
            max_size=5,
        )

    async def create_tables(self) -> None:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS character_links (
                discord_user_id BIGINT PRIMARY KEY,
                lodestone_id BIGINT NOT NULL,
                character_name TEXT NOT NULL,
                world TEXT NOT NULL,
                data_center TEXT NOT NULL
            );
            """
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def ping(self) -> int:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        return await self.pool.fetchval("SELECT 1")

    async def save_character_link(
        self,
        discord_user_id: int,
        lodestone_id: int,
        character_name: str,
        world: str,
        data_center: str,
    ) -> None:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        await self.pool.execute(
            """
            INSERT INTO character_links (
                discord_user_id,
                lodestone_id,
                character_name,
                world,
                data_center
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (discord_user_id)
            DO UPDATE SET
                lodestone_id = EXCLUDED.lodestone_id,
                character_name = EXCLUDED.character_name,
                world = EXCLUDED.world,
                data_center = EXCLUDED.data_center;
            """,
            discord_user_id,
            lodestone_id,
            character_name,
            world,
            data_center,
        )

    async def get_character_link(
        self,
        discord_user_id: int,
    ) -> asyncpg.Record | None:
        if self.pool is None:
            raise RuntimeError("Database is not connected.")

        return await self.pool.fetchrow(
            """
            SELECT
                discord_user_id,
                lodestone_id,
                character_name,
                world,
                data_center
            FROM character_links
            WHERE discord_user_id = $1;
            """,
            discord_user_id,
        )