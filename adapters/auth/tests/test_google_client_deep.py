"""
Deep unit tests for GoogleOAuthClient covering edge cases, network errors, and header validation.
"""

import httpx
import jwt
import pytest

from app.google_client import (
    GoogleAuthException,
    GoogleAuthTimeoutException,
    GoogleOAuthClient,
)


@pytest.mark.asyncio
async def test_get_client_lifecycle():
    client = GoogleOAuthClient()
    http_c = await client._get_client()
    assert isinstance(http_c, httpx.AsyncClient)
    assert not http_c.is_closed
    await http_c.aclose()


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_http_error():
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "Code expired"}
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleOAuthClient(http_client=http_client)
        with pytest.raises(GoogleAuthException) as exc_info:
            await client.exchange_code_for_tokens("test-code", "test-verifier")
        assert exc_info.value.status_code == 400
        assert "Code expired" in exc_info.value.message


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_network_error():
    async def mock_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection refused by Google")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleOAuthClient(http_client=http_client)
        with pytest.raises(GoogleAuthException) as exc_info:
            await client.exchange_code_for_tokens("test-code", "test-verifier")
        assert exc_info.value.status_code == 502
        assert "Network error" in exc_info.value.message


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_timeout():
    async def mock_handler(request: httpx.Request):
        raise httpx.ReadTimeout("Timeout")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleOAuthClient(http_client=http_client)
        with pytest.raises(GoogleAuthTimeoutException):
            await client.exchange_code_for_tokens("test-code", "test-verifier")


@pytest.mark.asyncio
async def test_get_google_jwks_success():
    fake_jwks = {"keys": [{"kid": "k1", "alg": "RS256"}]}

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_jwks)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleOAuthClient(http_client=http_client)
        jwks = await client.get_google_jwks()
        assert jwks == fake_jwks
        # Test cache hit
        jwks_cached = await client.get_google_jwks(force_refresh=False)
        assert jwks_cached == fake_jwks


@pytest.mark.asyncio
async def test_get_google_jwks_http_error():
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Google Server Error")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleOAuthClient(http_client=http_client)
        with pytest.raises(GoogleAuthException) as exc_info:
            await client.get_google_jwks()
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_get_google_jwks_network_error():
    async def mock_handler(request: httpx.Request):
        raise httpx.ConnectError("DNS failure")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleOAuthClient(http_client=http_client)
        with pytest.raises(GoogleAuthException) as exc_info:
            await client.get_google_jwks()
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_get_google_jwks_timeout():
    async def mock_handler(request: httpx.Request):
        raise httpx.ReadTimeout("Timeout")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleOAuthClient(http_client=http_client)
        with pytest.raises(GoogleAuthTimeoutException):
            await client.get_google_jwks()


@pytest.mark.asyncio
async def test_validate_id_token_empty_or_non_string():
    client = GoogleOAuthClient()
    with pytest.raises(GoogleAuthException, match="Missing or invalid"):
        await client.validate_id_token("")
    with pytest.raises(GoogleAuthException, match="Missing or invalid"):
        await client.validate_id_token(None)


@pytest.mark.asyncio
async def test_validate_id_token_malformed_header():
    client = GoogleOAuthClient()
    with pytest.raises(GoogleAuthException, match="Malformed"):
        await client.validate_id_token("not-a-token")


@pytest.mark.asyncio
async def test_validate_id_token_unsupported_algorithm():
    # Token with HS256 instead of RS256
    hs_token = jwt.encode({"sub": "123"}, key="secret", algorithm="HS256")
    client = GoogleOAuthClient()
    with pytest.raises(GoogleAuthException, match="Unsupported algorithm 'HS256'"):
        await client.validate_id_token(hs_token)


@pytest.mark.asyncio
async def test_validate_id_token_missing_kid():
    # Craft RS256 header without kid
    header_b64 = "eyJhbGciOiJSUzI1NiJ9"  # {"alg":"RS256"}
    payload_b64 = "eyJzdWIiOiIxMjMifQ"  # {"sub":"123"}
    fake_token = f"{header_b64}.{payload_b64}.c2ln"
    client = GoogleOAuthClient()
    with pytest.raises(GoogleAuthException, match="Missing key ID"):
        await client.validate_id_token(fake_token)
