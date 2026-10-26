import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import build_container
from app.main import create_app
from app.schemas import UserContext

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "test.db"), admin_token="test-admin-token", demo_mode=True)


@pytest.fixture
def container(settings):
    return build_container(settings)


@pytest.fixture
def user():
    return UserContext()


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))
