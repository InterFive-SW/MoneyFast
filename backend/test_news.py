import asyncio
from app.core.database import SessionLocal
from app.modules.news.service import send_briefing_to_user

async def main():
    db = SessionLocal()
    try:
        await send_briefing_to_user(db, user_id=1)
        print("Success")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
