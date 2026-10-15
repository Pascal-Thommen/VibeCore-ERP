"""
Pytest configuration and fixtures for Pagopar Payment Gateway Adapter test suite.
"""

import os
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pagopar.client import PagoparClient
from pagopar.config import Settings
from pagopar.database import get_db
from pagopar.db_models import Base
from pagopar.main import create_app
from pagopar.service import PagoparPaymentService

TEST_PUBLIC_KEY = "test_pub_key_9999"
TEST_PRIVATE_KEY = "test_priv_secret_8888"


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        pagopar_public_key=TEST_PUBLIC_KEY,
        pagopar_private_key=TEST_PRIVATE_KEY,
        pagopar_env="sandbox",
        pagopar_base_url="https://api-sandbox.pagopar.com",
        pagopar_checkout_base_url="https://sandbox.pagopar.com/pagos",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=2.0,
        max_retries=2,
    )


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client(db_engine, test_settings) -> Generator[TestClient, None, None]:
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    # Also override service settings
    import pagopar.router as router_module
    router_module.settings = test_settings
    router_module.service = PagoparPaymentService(
        client=PagoparClient(test_settings),
        custom_settings=test_settings,
    )

    with TestClient(app) as client:
        yield client
