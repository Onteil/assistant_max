"""Check action logs for ticket #36."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from constants import get_session
from sqlalchemy import select
from database.models import Action_Log


async def check_logs():
    """Check action logs for ticket #36."""
    async with get_session() as session:
        stmt = select(Action_Log).where(Action_Log.ticket_id == 36).order_by(Action_Log.action_timestamp.desc())
        result = await session.execute(stmt)
        logs = result.scalars().all()
        
        if logs:
            print(f"✅ Найдено {len(logs)} записей в логах для тикета #36:\n")
            for log in logs:
                print(f"  [{log.action_timestamp}] {log.action_type}")
                if log.action_details:
                    print(f"    Details: {log.action_details}")
                print()
        else:
            print("❌ Логи для тикета #36 не найдены")


if __name__ == "__main__":
    asyncio.run(check_logs())
