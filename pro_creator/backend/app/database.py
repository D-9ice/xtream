from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import text

from app.config import DATABASE_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    if IS_SQLITE:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(orchestrationjob)"))
            columns = {row[1] for row in result}
            if "task_id" not in columns:
                conn.execute(text("ALTER TABLE orchestrationjob ADD COLUMN task_id TEXT"))
            result = conn.execute(text("PRAGMA table_info(subscriptionaccount)"))
            subscription_columns = {row[1] for row in result}
            if "credits_reserved" not in subscription_columns:
                conn.execute(
                    text("ALTER TABLE subscriptionaccount ADD COLUMN credits_reserved INTEGER DEFAULT 0")
                )
            conn.commit()


def get_session():
    with Session(engine) as session:
        yield session
