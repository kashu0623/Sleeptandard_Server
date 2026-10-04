import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import raise_app_error
from app.models import User
from app.schemas import (
    AuthLoginRequest,
    AuthSignupRequest,
    AuthTokenResponse,
    AuthUserResponse,
)
from app.security import get_current_user
from app.services.auth import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("sleeptandard.auth")


def _auth_user_response(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        user_id=user.id,
        email=user.email or "",
        nickname=user.nickname or "",
        gender=user.gender,
        birthdate=user.birthdate,
    )


def _token_response(user: User) -> AuthTokenResponse:
    settings = get_settings()
    return AuthTokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expires_minutes * 60,
        user=_auth_user_response(user),
    )


@router.post(
    "/signup",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(
    request: AuthSignupRequest,
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    existing_user = db.scalar(select(User).where(User.email == request.email))
    if existing_user is not None:
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "EMAIL_ALREADY_EXISTS",
            "Email already exists",
        )

    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        nickname=request.nickname,
        gender=request.gender,
        birthdate=request.birthdate,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(
        "auth.signup_succeeded",
        extra={"user_id": user.id},
    )

    return _token_response(user)


@router.post("/login", response_model=AuthTokenResponse)
def login(
    request: AuthLoginRequest,
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    user = db.scalar(select(User).where(User.email == request.email))
    if user is None or not verify_password(request.password, user.password_hash):
        raise_app_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_LOGIN_CREDENTIALS",
            "Invalid email or password",
        )

    logger.info(
        "auth.login_succeeded",
        extra={"user_id": user.id},
    )
    return _token_response(user)


@router.get("/me", response_model=AuthUserResponse)
def me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return _auth_user_response(current_user)
