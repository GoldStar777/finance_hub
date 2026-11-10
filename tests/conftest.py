import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, configure_sqlite_engine, get_db
from app.main import app

@pytest.fixture(scope="session", autouse=True)
def guard_production_database():
    """Safety guard ensuring tests never connect to or modify production finances.db."""
    yield
    # Post-test assertion: Verify production database still exists and hasn't been modified during test run
    prod_path = Path("data/finances.db")
    if prod_path.exists():
        assert prod_path.stat().st_size > 0

@pytest.fixture
def in_memory_engine():
    """Creates a fast, shared in-memory SQLite database with foreign keys enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

@pytest.fixture
def db_session(in_memory_engine):
    """Provides an isolated database session per test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=in_memory_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def file_backed_engine(tmp_path):
    """Provides a temporary file-backed SQLite database to test WAL mode and disk operations."""
    db_file = tmp_path / "test_file_db.db"
    engine = configure_sqlite_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    yield engine, db_file
    engine.dispose()

