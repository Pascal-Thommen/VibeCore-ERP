"""
VibeCore ERP Auth Adapter - Google OAuth 2.0 & OIDC Auth Router.
Handles login initiation with PKCE (S256), callback token exchange, user profile verification, and logout.
"""

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
from fastapi.responses import RedirectResponse

from app.audit import log_audit_event
from app.config import settings
from app.google_client import (
    GoogleAuthException,
    GoogleAuthTimeoutException,
    GoogleOAuthClient,
)
from app.models import (
    ErrorResponse,
    LoginInitiationResponse,
    LogoutResponse,
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


# Dependency injection for Google OAuth client
def get_google_client() -> GoogleOAuthClient:
    return GoogleOAuthClient(app_settings=settings)


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
    client: GoogleOAuthClient = Depends(get_google_client),
):
    # 1. Generate RFC 7636 PKCE code_verifier and S256 code_challenge
    code_verifier = generate_code_verifier(64)
    code_challenge = compute_code_challenge(code_verifier)

    # 2. Generate tamper-proof HMAC signed state token
    state_payload = {
        "code_verifier": code_verifier,
        "redirect_after_login": redirect_after_login,
    }
    signed_state = create_signed_state(state_payload, secret_key=settings.cookie_secret)

    # 3. Build Google Authorization URL
    authorization_url = client.get_authorization_url(
        state=signed_state, code_challenge=code_challenge
    )

    log_audit_event(
        "auth.login.initiated",
        "Google login flow initiated with PKCE",
        data={"redirect_after_login": redirect_after_login},
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
            path="/",
        )
        return LoginInitiationResponse(
            authorization_url=authorization_url,
            state=signed_state,
        )

    redirect_resp = RedirectResponse(
        url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    redirect_resp.set_cookie(
        key=settings.cookie_state_name,
        value=signed_state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )
    return redirect_resp


@router.get(
    "/google/callback",
    response_model=TokenResponse,
    summary="Google OAuth 2.0 Authorization Callback & Token Exchange",
    description="Validates CSRF state, exchanges authorization code for tokens via PKCE, verifies Google ID token signatures, and issues VibeCore JWT.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid authorization code or state"},
        401: {"model": ErrorResponse, "description": "Token verification failure"},
        504: {"model": ErrorResponse, "description": "Google service timeout"},
    },
)
async def google_callback(
    request: Request,
    response: Response,
    code: str | None = Query(None, description="Google authorization code"),
    state: str | None = Query(None, description="Returned CSRF state parameter"),
    error: str | None = Query(None, description="Google OAuth error code if user declined"),
    error_description: str | None = Query(None, description="Google OAuth error description"),
    cookie_state: str | None = Cookie(None, alias=settings.cookie_state_name),
    client: GoogleOAuthClient = Depends(get_google_client),
):
    # 1. Handle user cancellation or Google authorization error
    if error:
        log_audit_event(
            "auth.callback.cancelled",
            f"Google login declined by user: {error}",
            data={"error": error, "description": error_description},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google login was cancelled or failed: {error_description or error}",
        )

    if not code:
        log_audit_event("auth.callback.missing_code", "Missing authorization code in callback")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'code' parameter in Google callback.",
        )

    if not state:
        log_audit_event("auth.callback.missing_state", "Missing state parameter in callback")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'state' parameter in Google callback.",
        )

    # 2. Verify state token HMAC signature and timestamp (CSRF protection)
    # If state cookie exists, ensure it matches state query param for double-submit protection
    if cookie_state and cookie_state != state:
        log_audit_event(
            "auth.callback.csrf_cookie_mismatch", "CSRF cookie does not match query parameter state"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF state mismatch between cookie and callback parameter.",
        )

    try:
        state_data = verify_signed_state(
            state, secret_key=settings.cookie_secret, max_age_seconds=600
        )
    except ValueError as exc:
        log_audit_event(
            "auth.callback.invalid_state", f"State verification failed: {exc}", exc_info=exc
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"CSRF verification failed: {exc}",
        ) from exc

    code_verifier = state_data.get("code_verifier")
    if not code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupted state: code_verifier missing.",
        )

    # 3. Exchange code for Google tokens with PKCE
    try:
        token_data = await client.exchange_code_for_tokens(code=code, code_verifier=code_verifier)
    except GoogleAuthTimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        ) from exc
    except GoogleAuthException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google token endpoint did not return an id_token.",
        )

    # 4. Validate Google ID token via Public JWKS (RS256, aud, iss, email_verified)
    try:
        claims = await client.validate_id_token(id_token)
    except GoogleAuthTimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        ) from exc
    except GoogleAuthException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    # 5. Map Google profile to VibeCore UserInfo and assign roles (ADR 0004)
    user_info = session_manager.create_user_info_from_google(claims)

    # 6. Issue VibeCore session JWT token
    access_token = session_manager.issue_session_token(user_info)

    # 7. Set secure session cookie and clear state cookie
    response.set_cookie(
        key=settings.cookie_session_name,
        value=access_token,
        max_age=settings.jwt_expiration_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )
    response.delete_cookie(
        key=settings.cookie_state_name,
        path="/",
    )

    log_audit_event(
        "auth.callback.success",
        f"User '{user_info.email}' successfully authenticated via Google SSO",
        data={"user_id": user_info.user_id, "roles": user_info.roles},
    )

    redirect_after_login = state_data.get("redirect_after_login")
    token_meta = {"redirect_after_login": redirect_after_login} if redirect_after_login else None

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.jwt_expiration_minutes * 60,
        user=user_info,
        meta=token_meta,
    )


@router.get(
    "/me",
    response_model=UserInfo,
    summary="Get Authenticated User Profile & Roles",
    description="Validates VibeCore session JWT from Bearer Authorization header or session cookie and returns userinfo.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or expired session token"},
    },
)
async def get_current_user(
    authorization: str | None = Header(None, alias="Authorization"),
    session_cookie: str | None = Cookie(None, alias=settings.cookie_session_name),
) -> UserInfo:
    token: str | None = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()

    if not token and session_cookie:
        token = session_cookie.strip()

    if not token:
        log_audit_event("auth.me.unauthorized", "Missing Bearer token or session cookie")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Bearer token or session cookie.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_info = session_manager.verify_session_token(token)
    except SessionException as exc:
        log_audit_event(
            "auth.me.invalid_token", f"Session token verification failed: {exc}", exc_info=exc
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    log_audit_event(
        "auth.me.success",
        f"Retrieved profile for user '{user_info.email}'",
        data={"user_id": user_info.user_id, "roles": user_info.roles},
    )
    return user_info


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Logout & Terminate Session",
    description="Clears session and state cookies, terminating the local user session.",
)
async def logout(response: Response) -> LogoutResponse:
    response.delete_cookie(key=settings.cookie_session_name, path="/")
    response.delete_cookie(key=settings.cookie_state_name, path="/")
    log_audit_event("auth.logout", "User logged out; session cookies deleted")
    return LogoutResponse(status="logged_out", message="Erfolgreich abgemeldet.")
