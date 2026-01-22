import asyncio

from sqlalchemy import text

from taggernews.infrastructure.database import async_session_factory


async def clear_data():
    async with async_session_factory() as session:
        # Clear in correct order (foreign key constraints)
        await session.execute(text("DELETE FROM story_tags"))
        await session.execute(text("DELETE FROM summaries"))
        await session.execute(text("DELETE FROM stories"))
        # Keep L1/L2 taxonomy, only clear misc tags
        await session.execute(text("DELETE FROM tags WHERE level > 2"))
        await session.commit()
        print("Database cleared! L1/L2 taxonomy preserved.")


asyncio.run(clear_data())
