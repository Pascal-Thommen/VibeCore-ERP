"""Pytest fixtures for Bancard vPOS 2.0 adapter test suite."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bancard.client import BancardGatewayClient
from bancard.database import Base, get_db
from bancard.service import BancardPaymentService


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
def db(db_engine):
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


class MockBancardGatewayClient(BancardGatewayClient):
    """Zero Mock compliance test client with controllable responses."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.should_fail = False
        self.failure_status_code = 502
        self.failure_message = "Gateway unavailable"

    def single_buy(self, shop_process_id, amount, currency, description, return_url=None, cancel_url=None):
        if self.should_fail:
            from bancard.client import BancardGatewayError
            raise BancardGatewayError(self.failure_message, status_code=self.failure_status_code)
        return {
            "status": "success",
            "process_id": f"proc_bancard_live_{shop_process_id}",
        }

    def cards_new(self, card_id, user_id, user_cell_phone=None, user_mail=None, return_url=None):
        if self.should_fail:
            from bancard.client import BancardGatewayError
            raise BancardGatewayError(self.failure_message, status_code=self.failure_status_code)
        return {
            "status": "success",
            "process_id": f"card_proc_live_{card_id}_{user_id}",
        }

    def charge(self, shop_process_id, amount, currency, alias_token, description):
        if self.should_fail:
            from bancard.client import BancardGatewayError
            raise BancardGatewayError(self.failure_message, status_code=self.failure_status_code)
        return {
            "status": "success",
            "confirmation": {
                "operation": {
                    "response_code": "00",
                    "response_description": "Transaccion aprobada",
                    "ticket_number": f"TKT_{shop_process_id}",
                    "authorization_number": f"AUTH_{shop_process_id}",
                }
            },
        }

    def rollback(self, shop_process_id):
        if self.should_fail:
            from bancard.client import BancardGatewayError
            raise BancardGatewayError(self.failure_message, status_code=self.failure_status_code)
        return {
            "status": "success",
            "messages": ["Rollback processed successfully"],
        }


@pytest.fixture
def mock_gateway_client():
    return MockBancardGatewayClient()


@pytest.fixture
def service(mock_gateway_client):
    svc = BancardPaymentService()
    svc.client = mock_gateway_client
    return svc
