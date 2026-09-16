from secrets import compare_digest

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import raise_app_error
from app.models import User
from app.services.auth import verify_access_token


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_header = HTTPBearer(auto_error=False)


def require_api_key(
    api_key: str | None = Depends(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_header),
) -> None:
    settings = get_settings()
    if api_key is not None:
        if compare_digest(api_key, settings.api_key):
            return
        raise_app_error(
            status.HTTP_403_FORBIDDEN,
            "INVALID_API_KEY",
            "Invalid API key",
        )

    if bearer is None:
        raise_app_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTHENTICATION_REQUIRED",
            "X-API-Key or Authorization bearer token is required",
        )

    token = bearer.credentials
    if compare_digest(token, settings.api_key):
        return
    if verify_access_token(token) is not None:
        return

    raise_app_error(
        status.HTTP_403_FORBIDDEN,
        "INVALID_API_KEY",
        "Invalid API key",
    )


def get_current_user(
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_header),
    db: Session = Depends(get_db),
) -> User:
    if bearer is None:
        raise_app_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTHENTICATION_REQUIRED",
            "Authorization bearer token is required",
        )

    user_id = verify_access_token(bearer.credentials)
    if user_id is None:
        raise_app_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_ACCESS_TOKEN",
            "Invalid or expired access token",
        )

    user = db.get(User, user_id)
    if user is None:
        raise_app_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_ACCESS_TOKEN",
            "Invalid or expired access token",
        )
    return user
