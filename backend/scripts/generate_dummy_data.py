import argparse
import random
import string
import uuid
import sys
import os
from datetime import datetime, timezone

# Add the parent directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.config import settings
from app.modules.auth.models import User

DUMMY_EMAIL_DOMAIN = "@dummy.moneyfast.local"
DUMMY_TC_PREFIX = "999"  # TC must be 11 digits, so we use 999 as prefix for dummy users


def is_safe_environment() -> bool:
    """Check if we are in a safe environment to generate dummy data."""
    # This prevents running in production by checking the DB URL
    safe_indicators = ["localhost", "127.0.0.1", "test", "sqlite"]
    db_url = str(settings.DATABASE_URL).lower()
    return any(indicator in db_url for indicator in safe_indicators)


def generate_dummy_data(users_count: int, seed: int = None, reset: bool = False):
    """Generate dummy data for the application."""
    if not is_safe_environment():
        print("ERROR: Cannot run generator in a non-development environment.")
        print(f"DATABASE_URL ({settings.DATABASE_URL}) does not look like a local/test DB.")
        sys.exit(1)

    if seed is not None:
        random.seed(seed)

    db = SessionLocal()
    try:
        if reset:
            print("Resetting existing dummy data...")
            # We identify dummy data by the email domain
            deleted_count = db.query(User).filter(User.email.endswith(DUMMY_EMAIL_DOMAIN)).delete()
            db.commit()
            print(f"Deleted {deleted_count} dummy user(s).")
            # We don't exit here, we continue to generate new data if requested, 
            # unless users_count is 0.
            if users_count <= 0:
                return

        print(f"Generating {users_count} dummy users...")
        users_added = 0
        
        # Determine the starting index for TC numbers to avoid conflicts if not resetting
        existing_dummy_users_count = db.query(User).filter(User.tc_no.startswith(DUMMY_TC_PREFIX)).count()
        start_idx = existing_dummy_users_count + 1

        for i in range(users_count):
            idx = start_idx + i
            
            # Generate deterministic but unique TC number
            tc_no = f"{DUMMY_TC_PREFIX}{idx:08d}"
            
            # Generate phone number (10-15 digits, starting with +)
            phone_number = f"+90555{idx:07d}"
            
            first_name = random.choice(["Ahmet", "Mehmet", "Ayşe", "Fatma", "Ali", "Zeynep", "Mustafa", "Elif", "Can", "Cem"])
            last_name = random.choice(["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Öztürk", "Arslan", "Doğan", "Kılıç"])
            
            email = f"user.{idx}{DUMMY_EMAIL_DOMAIN}"
            
            # Generate a standard password that passes validation
            # Password must be at least 8 chars, 1 uppercase, 1 digit
            raw_password = f"Password{idx}"
            
            user = User(
                tc_no=tc_no,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone_number,
                hashed_password=hash_password(raw_password),
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            db.add(user)
            users_added += 1

        db.commit()
        print(f"Successfully generated {users_added} dummy users.")

    except Exception as e:
        db.rollback()
        print(f"An error occurred: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate dummy data for MoneyFast development.")
    parser.add_argument("--users", type=int, default=10, help="Number of dummy users to generate (default: 10)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for deterministic generation")
    parser.add_argument("--reset", action="store_true", help="Delete existing dummy data before generating")
    
    args = parser.parse_args()
    
    generate_dummy_data(users_count=args.users, seed=args.seed, reset=args.reset)
