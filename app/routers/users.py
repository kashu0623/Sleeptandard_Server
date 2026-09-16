import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import raise_app_error
from app.models import SleepSession, SleepSummary, User
from app.schemas import (
    UserCreateRequest,
    UserResponse,
    UserSleepSessionListItem,
    UserSleepSessionListResponse,
)
from app.security import get_current_user, require_api_key


router = APIRouter(
    prefix="/users",
    tags=["users"],
)


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        beta_code=user.beta_code,
        email=user.email,
        nickname=user.nickname,
        gender=user.gender,
        birthdate=user.birthdate,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def ensure_email_is_available(
    db: Session,
    email: str | None,
    current_user_id: uuid.UUID | None = None,
) -> None:
    if email is None:
        return

    query = select(User).where(User.email == email)
    if current_user_id is not None:
        query = query.where(User.id != current_user_id)

    if db.scalar(query) is not None:
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "EMAIL_ALREADY_EXISTS",
            "Email already exists",
        )


def apply_user_profile(user: User, request: UserCreateRequest) -> None:
    if "email" in request.model_fields_set:
        user.email = request.email
    if "nickname" in request.model_fields_set:
        user.nickname = request.nickname
    if "gender" in request.model_fields_set:
        user.gender = request.gender
    if "birthdate" in request.model_fields_set:
        user.birthdate = request.birthdate


def ensure_current_user_matches_path(current_user: User, user_id: uuid.UUID) -> None:
    if current_user.id != user_id:
        raise_app_error(
            status.HTTP_403_FORBIDDEN,
            "USER_FORBIDDEN",
            "You can access only your own user data",
        )


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_user(
    request: UserCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    user = db.scalar(select(User).where(User.beta_code == request.beta_code))
    if user is not None:
        ensure_email_is_available(db, request.email, current_user_id=user.id)
        apply_user_profile(user, request)
        db.commit()
        db.refresh(user)
        response.status_code = status.HTTP_200_OK
        return to_user_response(user)

    ensure_email_is_available(db, request.email)

    user = User(beta_code=request.beta_code)
    apply_user_profile(user, request)
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_user_response(user)


@router.get(
    "/{user_id}/sleep-sessions",
    response_model=UserSleepSessionListResponse,
)
def list_user_sleep_sessions(
    user_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSleepSessionListResponse:
    ensure_current_user_matches_path(current_user, user_id)
    user = db.get(User, user_id)
    if user is None:
        raise_app_error(
            status.HTTP_404_NOT_FOUND,
            "USER_NOT_FOUND",
            "User not found",
        )

    total_count = db.scalar(
        select(func.count()).select_from(SleepSession).where(SleepSession.user_id == user.id)
    )
    rows = db.execute(
        select(SleepSession, SleepSummary)
        .outerjoin(SleepSummary, SleepSummary.sleep_session_id == SleepSession.id)
        .where(SleepSession.user_id == user.id)
        .order_by(desc(SleepSession.started_at))
        .limit(limit)
        .offset(offset)
    ).all()

    return UserSleepSessionListResponse(
        user_id=user.id,
        total_count=total_count or 0,
        limit=limit,
        offset=offset,
        sleep_sessions=[
            UserSleepSessionListItem(
                session_id=sleep_session.id,
                device_id=sleep_session.device_id,
                started_at=sleep_session.started_at,
                ended_at=sleep_session.ended_at,
                duration_sec=sleep_session.duration_sec,
                session_status=sleep_session.session_status,
                upload_status=sleep_session.upload_status,
                sleep_score=sleep_summary.sleep_score if sleep_summary is not None else None,
                total_sleep_sec=(
                    sleep_summary.total_sleep_sec if sleep_summary is not None else None
                ),
            )
            for sleep_session, sleep_summary in rows
        ],
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    ensure_current_user_matches_path(current_user, user_id)
    user = db.get(User, user_id)
    if user is None:
        raise_app_error(
            status.HTTP_404_NOT_FOUND,
            "USER_NOT_FOUND",
            "User not found",
        )
    return to_user_response(user)
