"""Seed the database with synthetic demo data (development only).

Run from backend/:  uv run python -m scripts.seed
"""

import os
from datetime import datetime, time

from argon2 import PasswordHasher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    AvailabilityBlock,
    AvailabilitySlot,
    LawyerProfile,
    User,
)

DEMO_PASSWORD = "Demo12345!"  # fake password, demo accounts only

# weekday: 0 = Sunday ... 6 = Saturday
USERS = [
    {
        "full_name": "Demo Admin",
        "email": "admin@tawkeel.test",
        "role": "admin",
    },
    {
        "full_name": "Mohammed Elgazar",
        "email": "mohammed_g.client@tawkeel.test",
        "role": "client",
    },
    {
        "full_name": "Mariam Amgad",
        "email": "mariam.client@tawkeel.test",
        "role": "client",
    },
    {
        "full_name": "Manal Anwer",
        "email": "manal_anwer.lawyer@tawkeel.test",
        "role": "lawyer",
        "profile": {
            "niches": ["labor", "civil"],
            "city": "Cairo",
            "fee_min": 300,
            "fee_max": 600,
            "years_experience": 8,
            "bio": "Labor and civil disputes.",
            "verified": True,
        },
        "slots": [(0, time(10), time(14)), (2, time(10), time(14))],
    },
    {
        "full_name": "Esraa Alaa",
        "email": "esraa_basic.lawyer@tawkeel.test",
        "role": "lawyer",
        "profile": {
            "niches": ["personal_status"],
            "city": "Tanta",
            "fee_min": 200,
            "fee_max": 400,
            "years_experience": 5,
            "bio": "Family and personal status cases.",
            "verified": True,
        },
        "slots": [(1, time(12), time(17)), (3, time(12), time(17))],
    },
    {
        "full_name": "Noura shousha",
        "email": "nr_shousha.lawyer@tawkeel.test",
        "role": "lawyer",
        "profile": {
            "niches": ["commercial", "real_estate"],
            "city": "Alexandria",
            "fee_min": 800,
            "fee_max": 1500,
            "years_experience": 15,
            "bio": "Commercial contracts and real estate.",
            "verified": True,
        },
        "slots": [(0, time(9), time(13)), (4, time(9), time(13))],
    },
    {
        "full_name": "Omar shaheen",
        "email": "omar_sh.lawyer@tawkeel.test",
        "role": "lawyer",
        "profile": {
            "niches": ["criminal"],
            "city": "Cairo",
            "fee_min": 500,
            "fee_max": 1000,
            "years_experience": 10,
            "bio": "Criminal defense.",
            "verified": False,  # not yet verified by the admin
        },
        "slots": [(2, time(15), time(19)), (4, time(15), time(19))],
    },
]


def get_engine():
    url = os.environ["DATABASE_URL"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    return create_engine(url)


def seed(session: Session) -> int:
    hasher = PasswordHasher()
    created = 0

    for data in USERS:
        exists = session.scalar(select(User).where(User.email == data["email"]))
        if exists:
            continue

        user = User(
            full_name=data["full_name"],
            email=data["email"],
            role=data["role"],
            password_hash=hasher.hash(DEMO_PASSWORD),
        )
        session.add(user)
        session.flush()  # gives the user its id

        if data["role"] == "lawyer":
            profile = LawyerProfile(user_id=user.id, **data["profile"])
            session.add(profile)
            session.flush()

            for weekday, start, end in data["slots"]:
                session.add(
                    AvailabilitySlot(
                        lawyer_id=profile.id,
                        weekday=weekday,
                        start_time=start,
                        end_time=end,
                    )
                )

            # one example blocked period (a court day)
            session.add(
                AvailabilityBlock(
                    lawyer_id=profile.id,
                    starts_at=datetime(2026, 12, 1, 9, 0),
                    ends_at=datetime(2026, 12, 1, 17, 0),
                    reason="court",
                )
            )

        created += 1

    session.commit()
    return created


def main() -> None:
    engine = get_engine()
    with Session(engine) as session:
        created = seed(session)
    print(f"Seed finished: {created} new users created.")


if __name__ == "__main__":
    main()
