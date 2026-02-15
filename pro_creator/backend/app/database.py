from threading import Lock

from sqlmodel import Session, create_engine

from app.config import DATABASE_URL
from app.migrations import upgrade_head

IS_SQLITE = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

_init_lock = Lock()
_did_init = False


def init_db() -> None:
    # Run schema migrations (idempotent).
    upgrade_head(engine)

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
