"""
Pytest configuration and fixtures for Stripe Payment Gateway Adapter test suite.
"""

from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from stripe_adapter.client import StripeClient
from stripe_adapter.config import Settings
from stripe_adapter.database import get_db
from stripe_adapter.db_models import Base
from stripe_adapter.main import create_app
from stripe_adapter.service import StripePaymentService

TEST_SECRET_KEY = "sk_test_testsecretkey9999"
TEST_PUBLISHABLE_KEY = "pk_test_testpubkey8888"
TEST_WEBHOOK_SECRET = "whsec_testwebhooksecret7777"


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        stripe_secret_key=TEST_SECRET_KEY,
        stripe_publishable_key=TEST_PUBLISHABLE_KEY,
        stripe_webhook_secret=TEST_WEBHOOK_SECRET,
        stripe_default_currency="USD",
        stripe_env="sandbox",
        stripe_base_url="https://api.stripe.com",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=2.0,
        max_retries=2,
        webhook_tolerance_seconds=300,
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

    import stripe_adapter.router as router_module
    router_module.settings = test_settings
    router_module.service = StripePaymentService(
        client=StripeClient(test_settings),
        custom_settings=test_settings,
    )

    with TestClient(app) as client:
        yield client
