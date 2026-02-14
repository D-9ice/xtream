from threading import Lock

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import text, inspect

from app.config import DATABASE_URL
from app.models import AppSettings

IS_SQLITE = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

_init_lock = Lock()
_did_init = False


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    inspector = inspect(engine)
    with engine.connect() as conn:
        try:
            columns = {col["name"] for col in inspector.get_columns("orchestrationjob")}
            if "task_id" not in columns:
                conn.execute(text("ALTER TABLE orchestrationjob ADD COLUMN task_id TEXT"))
        except Exception:
            pass

        try:
            subscription_columns = {col["name"] for col in inspector.get_columns("subscriptionaccount")}
            if "credits_reserved" not in subscription_columns:
                conn.execute(
                    text("ALTER TABLE subscriptionaccount ADD COLUMN credits_reserved INTEGER DEFAULT 0")
                )
        except Exception:
            pass

        # Ensure singleton settings row exists.
        try:
            conn.execute(
                text(
                    "INSERT INTO appsettings (id, auth_required, created_at, updated_at) "
                    "SELECT 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                    "WHERE NOT EXISTS (SELECT 1 FROM appsettings WHERE id = 1)"
                )
            )
        except Exception:
            pass
        conn.commit()

def _ensure_init() -> None:
    global _did_init
    if _did_init:
        return
    with _init_lock:
        if _did_init:
            return
        init_db()
        _did_init = True


def get_session():
    _ensure_init()
    with Session(engine) as session:
        yield session
