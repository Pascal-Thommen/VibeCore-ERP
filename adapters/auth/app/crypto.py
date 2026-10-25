"""
VibeCore ERP Auth Adapter - Cryptographic Key & JWKS Manager.
Provides asymmetric key generation, PEM loading, RS256/EdDSA JWT signing,
verification, and public JWKS (RFC 7517) publication for stateless token validation.
"""

import json
import os
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
import jwt
from jwt.algorithms import OKPAlgorithm, RSAAlgorithm

from app.audit import log_audit_event
from app.config import Settings
from app.config import settings as default_settings


class CryptoException(Exception):
    """Base exception for cryptographic operations."""

    def __init__(self, message: str, detail: str | None = None, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status_code = status_code


class CryptoManager:
    """
    Manages asymmetric key pairs (RS256 / EdDSA) for the VibeCore Auth IdP service.
    Exposes JWKS endpoint data and handles cryptographic signing and verification.
    """

    def __init__(self, app_settings: Settings | None = None):
        self.settings = app_settings or default_settings
        raw_alg = (self.settings.jwt_algorithm or "").strip()
        if raw_alg.upper() == "EDDSA":
            self.algorithm = "EdDSA"
        else:
            self.algorithm = "RS256"
        self.key_id = self.settings.jwt_key_id

        # Internal key holders
        self._private_key: Any = None
        self._public_key: Any = None
        self._jwk_cache: dict[str, Any] | None = None

        self._initialize_keys()

    def _initialize_keys(self) -> None:
        """
        Loads the private key from PEM string, PEM file, or generates a new asymmetric keypair.
        """
        # 1. Try loading from PEM string in config
        if self.settings.jwt_private_key_pem:
            pem_bytes = self.settings.jwt_private_key_pem.encode("utf-8")
            self._private_key = serialization.load_pem_private_key(pem_bytes, password=None)
            self._public_key = self._private_key.public_key()
            return

        # 2. Try loading from PEM file path in config
        if self.settings.jwt_private_key_path and os.path.exists(
            self.settings.jwt_private_key_path
        ):
            with open(self.settings.jwt_private_key_path, "rb") as f:
                pem_bytes = f.read()
            self._private_key = serialization.load_pem_private_key(pem_bytes, password=None)
            self._public_key = self._private_key.public_key()
            return

        # 3. Generate keypair based on algorithm
        if self.algorithm.upper() == "EDDSA":
            self.algorithm = "EdDSA"
            self._private_key = ed25519.Ed25519PrivateKey.generate()
            self._public_key = self._private_key.public_key()
        else:
            # Default to RS256 (RSA 2048-bit)
            self.algorithm = "RS256"
            self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self._public_key = self._private_key.public_key()

        log_audit_event(
            "crypto.keypair_initialized",
            f"Initialized asymmetric keypair with algorithm {self.algorithm} and kid {self.key_id}",
            data={"algorithm": self.algorithm, "kid": self.key_id},
        )

    def get_public_key_pem(self) -> str:
        """Returns the public key serialized as PEM string."""
        pem_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem_bytes.decode("utf-8")

    def get_jwk(self) -> dict[str, Any]:
        """
        Returns the public key in standard RFC 7517 JWK format.
        """
        if self._jwk_cache is not None:
            return self._jwk_cache

        if self.algorithm.upper() == "EDDSA":
            raw_jwk = OKPAlgorithm.to_jwk(self._public_key)
            jwk = json.loads(raw_jwk) if isinstance(raw_jwk, str) else raw_jwk
            jwk["alg"] = "EdDSA"
        else:
            raw_jwk = RSAAlgorithm.to_jwk(self._public_key)
            jwk = json.loads(raw_jwk) if isinstance(raw_jwk, str) else raw_jwk
            jwk["alg"] = "RS256"

        jwk["kid"] = self.key_id
        jwk["use"] = "sig"
        self._jwk_cache = jwk
        return jwk

    def get_jwks(self) -> dict[str, list[dict[str, Any]]]:
        """
        Returns the standard RFC 7517 JWKS dictionary for the /.well-known/jwks.json endpoint.
        """
        return {"keys": [self.get_jwk()]}

    def sign(self, payload: dict[str, Any], headers: dict[str, Any] | None = None) -> str:
        """
        Signs a payload into a JWT using the private key and configured algorithm.
        Always injects kid into the JWT header.
        """
        jwt_headers = {"kid": self.key_id, "typ": "JWT"}
        if headers:
            jwt_headers.update(headers)

        token = jwt.encode(
            payload,
            key=self._private_key,
            algorithm=self.algorithm,
            headers=jwt_headers,
        )
        return token

    def verify(
        self,
        token: str,
        expected_issuer: str | None = None,
        expected_audience: str | None = None,
        leeway: int = 10,
    ) -> dict[str, Any]:
        """
        Verifies and decodes a token using the public key.
        Validates signature, expiration, issuer, and audience.
        """
        if not token or not isinstance(token, str):
            raise CryptoException("Token must be a non-empty string.")

        try:
            # First extract header to check algorithm and kid
            unverified_header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise CryptoException("Malformed JWT header.", detail=str(exc)) from exc

        token_alg = unverified_header.get("alg")
        if token_alg != self.algorithm:
            raise CryptoException(
                f"Unsupported token algorithm: '{token_alg}'. Expected '{self.algorithm}'."
            )

        token_kid = unverified_header.get("kid")
        if token_kid and token_kid != self.key_id:
            log_audit_event(
                "crypto.unknown_kid",
                f"Token signed with unknown kid: {token_kid}",
                data={"token_kid": token_kid, "expected_kid": self.key_id},
            )

        require_claims = ["exp", "sub"]
        if expected_issuer:
            require_claims.append("iss")
        if expected_audience:
            require_claims.append("aud")

        try:
            claims = jwt.decode(
                token,
                key=self._public_key,
                algorithms=[self.algorithm],
                issuer=expected_issuer,
                audience=expected_audience,
                options={
                    "require": require_claims,
                    "verify_exp": True,
                    "verify_aud": bool(expected_audience),
                    "verify_iss": bool(expected_issuer),
                },
                leeway=leeway,
            )
            return claims
        except jwt.ExpiredSignatureError as exc:
            raise CryptoException("Token has expired.", detail=str(exc), status_code=401) from exc
        except jwt.InvalidIssuerError as exc:
            raise CryptoException("Invalid token issuer.", detail=str(exc), status_code=401) from exc
        except jwt.InvalidAudienceError as exc:
            raise CryptoException(
                "Invalid token audience.", detail=str(exc), status_code=401
            ) from exc
        except jwt.PyJWTError as exc:
            raise CryptoException(
                "Invalid token cryptographic signature.", detail=str(exc), status_code=401
            ) from exc


crypto_manager = CryptoManager()
