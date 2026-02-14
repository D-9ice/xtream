from passlib.context import CryptContext
from sqlmodel import Session, select

from app.config import ADMIN_EMAIL, ADMIN_PASSWORD
from app.database import engine
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed_admin_user() -> None:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == ADMIN_EMAIL)).first()
        if existing:
            return
        user = User(
            email=ADMIN_EMAIL,
            hashed_password=pwd_context.hash(ADMIN_PASSWORD),
            role="admin",
        )
        session.add(user)
        session.commit()
