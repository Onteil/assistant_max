"""Check enum values in database."""
import asyncio
from sqlalchemy import text
from database.session import init_db
from constants import DB_URL


async def check_enum():
    db = init_db(DB_URL)
    async with db.session() as session:
        result = await session.execute(
            text("SELECT unnest(enum_range(NULL::actiontype))")
        )
        values = [row[0] for row in result]
        print("ActionType enum values in database:")
        for v in values:
            print(f"  - {v}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(check_enum())
