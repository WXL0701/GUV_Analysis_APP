import sys
import pytest
from typing import Generator
import uuid
import json

# Monkey patch sqlalchemy.dialects.postgresql BEFORE importing app components
# This allows using SQLite for testing even though models import Postgres-specific types
from sqlalchemy.types import TypeDecorator, CHAR, Text
import sqlalchemy.dialects.postgresql

class MockUUID(TypeDecorator):
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)

class MockJSONB(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)

# Apply patches
sqlalchemy.dialects.postgresql.UUID = MockUUID
sqlalchemy.dialects.postgresql.JSONB = MockJSONB

# Now import app components
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.api import deps
from app.db.models import User

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def db() -> Generator:
    # Create tables
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="module")
def client(db) -> Generator:
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    # Override current_user to always return a mock admin user
    def override_get_current_user():
        return User(id=uuid.uuid4(), username="testadmin", role="admin")

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = override_get_current_user
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()
