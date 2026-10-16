"""
VibeCore ERP Auth Adapter - Google OAuth 2.0 & OIDC Auth Router.
Handles login initiation with PKCE (S256), callback token exchange, user profile verification,
stateless token refresh, and public JWKS endpoint.
"""

from typing import Optional

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse

from app.audit import log_audit_event
from app.config import settings
from app.crypto import crypto_manager
from app.google_client import (
    GoogleAuthException,
    GoogleAuthTimeoutException,
    GoogleOAuthClient,
)
from app.metrics import metrics_registry
from app.models import (
    ErrorResponse,
    JWKSResponse,
    LoginInitiationResponse,
    LogoutResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserInfo,
)
from app.pkce import (
    compute_code_challenge,
    create_signed_state,
    generate_code_verifier,
    verify_signed_state,
)
from app.session import SessionException, session_manager

router = APIRouter(prefix="/auth", tags=["Google OAuth 2.0 & OIDC SSO"])


def get_google_client() -> GoogleOAuthClient:
    return GoogleOAuthClient(app_settings=settings)


@router.get(
    "/.well-known/jwks.json",
    response_model=JWKSResponse,
    summary="Public JWKS Key Set",
    description="Returns RFC 7517 JSON Web Key Set containing active public signing keys for stateless validation.",
)
async def get_auth_jwks() -> JWKSResponse:
    jwks = crypto_manager.get_jwks()
    return JWKSResponse(keys=jwks["keys"])


@router.get(
    "/google/login",
    response_model=LoginInitiationResponse,
    summary="Initiate Google OAuth 2.0 Login with PKCE",
    description="Generates PKCE verifier, computes S256 challenge, signs CSRF state, and redirects to Google.",
    responses={
        307: {"description": "Redirect to Google Accounts Authorization Endpoint"},
        200: {
            "model": LoginInitiationResponse,
            "description": "JSON payload with authorization URL when requested",
        },
    },
)
async def google_login(
    request: Request,
    response: Response,
    redirect_after_login: str | None = Query(
        None, description="Client redirect URI upon login completion"
    ),
    org_hint: str | None = Query(
        None, description="Optional organization or tenant hint for user assignment"
    ),
    client: GoogleOAuthClient = Depends(get_google_client),
):
    # 1. Generate RFC 7636 PKCE code_verifier and S256 code_challenge
    code_verifier = generate_code_verifier(64)
    code_challenge = compute_code_challenge(code_verifier)

    # 2. Generate tamper-proof HMAC signed state token
    state_payload = {
        "code_verifier": code_verifier,
        "redirect_after_login": redirect_after_login,
        "org_hint": org_hint,
    }
    signed_state = create_signed_state(state_payload, secret_key=settings.cookie_secret)

    # 3. Build Google Authorization URL
    authorization_url = client.get_authorization_url(
        state=signed_state, code_challenge=code_challenge
    )

    log_audit_event(
        "auth.login.initiated",
        "Google login flow initiated with PKCE",
        data={"redirect_after_login": redirect_after_login, "org_hint": org_hint},
    )

    # 4. Set secure HttpOnly state cookie
    accept_header = request.headers.get("accept", "")
    wants_json = "application/json" in accept_header and "text/html" not in accept_header

    if wants_json:
        response.set_cookie(
            key=settings.cookie_state_name,
            value=signed_state,
            max_age=600,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_same_site,
            path="/auth",
        )
        return LoginInitiationResponse(
            authorization_url=authorization_url,
            state=signed_state,
            meta={"org_hint": org_hint},
        )

    redirect_resp = RedirectResponse(url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    redirect_resp.set_cookie(
        key=settings.cookie_state_name,
        value=signed_state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/auth",
    )
    return redirect_resp


@router.get(
    "/google/callback",
    response_model=TokenResponse,
    summary="Google OAuth 2.0 Callback & Code Exchange",
    description="Validates CSRF state, exchanges auth code via PKCE, verifies Google ID Token signature, assigns tenant, and issues RS256 token pair.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid authorization code or state token"},
        401: {"model": ErrorResponse, "description": "Google signature validation failure"},
        504: {"model": ErrorResponse, "description": "Timeout contacting Google OAuth API"},
    },
)
async def google_callback(
    response: Response,
    code: str | None = Query(None, description="Authorization code from Google"),
    state: str | None = Query(None, description="CSRF state parameter"),
    error: str | None = Query(None, description="Google OAuth error if user cancelled"),
    error_description: str | None = Query(None, description="Google OAuth error description"),
    state_cookie: str | None = Cookie(None, alias=settings.cookie_state_name),
    client: GoogleOAuthClient = Depends(get_google_client),
):
    # 1. Handle error returned by Google
    if error:
        log_audit_event(
            "auth.google.cancelled",
            f"Google login was cancelled or failed: {error} ({error_description})",
            data={"error": error, "description": error_description},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google login was cancelled or failed: {error_description or error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'code' parameter in Google callback.",
        )

    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'state' parameter in Google callback.",
        )

    # 2. Verify HMAC-signed CSRF state parameter
    try:
        state_data = verify_signed_state(state, secret_key=settings.cookie_secret)
    except Exception as exc:
        log_audit_event("auth.csrf.failed", f"State verification failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid CSRF state signature: potential tampering ({exc})",
        ) from exc

    # Cross-verify with state cookie if cookie was transmitted
    if state_cookie and state_cookie != state:
        log_audit_event("auth.csrf.cookie_mismatch", "CSRF state cookie did not match query parameter")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF state cookie mismatch. Potential cross-site request forgery.",
        )

    code_verifier = state_data.get("code_verifier")
    org_hint = state_data.get("org_hint")
    if not code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state payload: missing PKCE code_verifier.",
        )

    # 3. Server-side token exchange with Google OAuth endpoint (Säule 1)
    try:
        tokens = await client.exchange_code_for_tokens(code=code, code_verifier=code_verifier)
    except GoogleAuthTimeoutException as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=exc.message) from exc
    except GoogleAuthException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google token response did not contain an id_token.",
        )

    # 4. Validate Google ID Token RS256 signature and claims against Google Public JWKS
    try:
        claims = await client.validate_id_token(id_token)
    except GoogleAuthException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # 5. Transform claims and resolve tenant
    user_info = session_manager.create_user_info_from_google(claims, org_hint=org_hint)

    # 6. Issue VibeCore RS256 token pair (Access Token + Refresh Token)
    token_response = session_manager.issue_token_pair(user_info)

    # 7. Set secure session cookies
    response.set_cookie(
        key=settings.cookie_session_name,
        value=token_response.access_token,
        max_age=settings.jwt_expiration_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )
    response.set_cookie(
        key="vibecore_refresh_token",
        value=token_response.refresh_token,
        max_age=settings.jwt_refresh_expiration_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/auth",
    )

    # Delete temporary state cookie
    response.delete_cookie(key=settings.cookie_state_name, path="/auth")

    log_audit_event(
        "auth.callback.success",
        f"User {user_info.email} successfully logged in for tenant {user_info.tenant_id}",
        data={
            "user_id": user_info.user_id,
            "email": user_info.email,
            "tenant_id": user_info.tenant_id,
            "roles": user_info.roles,
        },
    )

    return token_response


@router.post(
    "/token/refresh",
    response_model=TokenResponse,
    summary="Refresh VibeCore Session Tokens",
    description="Validates cryptographic signature of refresh token and issues a new access token and rotated refresh token.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid token type or missing refresh token"},
        401: {"model": ErrorResponse, "description": "Expired or invalid refresh token signature"},
    },
)
async def refresh_token(
    request: Request,
    response: Response,
    req: RefreshTokenRequest | None = None,
    cookie_refresh_token: str | None = Cookie(None, alias="vibecore_refresh_token"),
):
    refresh_token_val: str | None = None
    tenant_hint: str | None = None

    if req and req.refresh_token:
        refresh_token_val = req.refresh_token.strip()
        tenant_hint = req.tenant_hint
    elif cookie_refresh_token:
        refresh_token_val = cookie_refresh_token.strip()

    if not refresh_token_val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required via request body or cookie.",
        )

    try:
        new_token_response = session_manager.refresh_session(
            refresh_token=refresh_token_val, tenant_hint=tenant_hint
        )
    except SessionException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # Update cookies
    response.set_cookie(
        key=settings.cookie_session_name,
        value=new_token_response.access_token,
        max_age=settings.jwt_expiration_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )
    if new_token_response.refresh_token:
        response.set_cookie(
            key="vibecore_refresh_token",
            value=new_token_response.refresh_token,
            max_age=settings.jwt_refresh_expiration_days * 86400,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_same_site,
            path="/auth",
        )

    return new_token_response


@router.get(
    "/me",
    response_model=UserInfo,
    summary="Get Authenticated User Profile & Roles",
    description="Validates Bearer token or session cookie and returns user profile, tenant ID, and assigned roles.",
    responses={
        401: {"model": ErrorResponse, "description": "Missing, expired, or invalid session token"}
    },
)
async def get_me(
    authorization: str | None = Header(None, alias="Authorization"),
    session_cookie: str | None = Cookie(None, alias=settings.cookie_session_name),
):
    token: str | None = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    elif session_cookie:
        token = session_cookie.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials. Provide Bearer token or session cookie.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_info = session_manager.verify_session_token(token)
    except SessionException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return user_info


@router.post(
    "/verify",
    response_model=UserInfo,
    summary="Stateless Token Verification",
    description="Verifies an access token and returns verified identity and tenant info.",
)
async def verify_token_endpoint(
    token: str | None = Query(None, description="Access token to verify"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    token_str = token
    if not token_str and authorization and authorization.startswith("Bearer "):
        token_str = authorization.split("Bearer ", 1)[1].strip()

    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is required via query parameter or Bearer authorization.",
        )

    try:
        user_info = session_manager.verify_session_token(token_str)
        return user_info
    except SessionException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Log Out and Clear Session",
    description="Clears session cookies and invalidates local authentication state.",
)
async def logout(response: Response):
    response.delete_cookie(key=settings.cookie_session_name, path="/")
    response.delete_cookie(key="vibecore_refresh_token", path="/auth")
    response.delete_cookie(key=settings.cookie_state_name, path="/auth")

    log_audit_event("auth.logout", "User session logged out successfully")
    return LogoutResponse()
