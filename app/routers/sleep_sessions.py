import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import raise_app_error
from app.models import AlarmEvent, Device, SleepSession, SleepSummary, User
from app.schemas import (
    AlarmEventCreateRequest,
    AlarmEventCreateResponse,
    AlarmEventRead,
    SleepSessionAbortRequest,
    SleepSessionAbortResponse,
    SleepSessionDetailResponse,
    SleepSessionFinishRequest,
    SleepSessionFinishResponse,
    SleepSessionStartRequest,
    SleepSessionStartResponse,
    SleepSessionUploadUpdateRequest,
    SleepSessionUploadUpdateResponse,
    SleepSessionUploadUrlRequest,
    SleepSessionUploadUrlResponse,
    SleepSummaryRead,
    SleepSummarySaveRequest,
    SleepSummarySaveResponse,
)
from app.config import get_settings
from app.security import get_current_user
from app.services.s3 import create_presigned_upload_url


router = APIRouter(
    prefix="/sleep-sessions",
    tags=["sleep_sessions"],
)
logger = logging.getLogger("sleeptandard.sleep_session")


def get_owned_sleep_session(
    db: Session,
    session_id: uuid.UUID,
    current_user: User,
) -> SleepSession:
    sleep_session = db.get(SleepSession, session_id)
    if sleep_session is None:
        raise_app_error(
            status.HTTP_404_NOT_FOUND,
            "SLEEP_SESSION_NOT_FOUND",
            "Sleep session not found",
        )
    if sleep_session.user_id != current_user.id:
        raise_app_error(
            status.HTTP_403_FORBIDDEN,
            "SLEEP_SESSION_FORBIDDEN",
            "You can access only your own sleep sessions",
        )
    return sleep_session


@router.post(
    "/start",
    response_model=SleepSessionStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_sleep_session(
    request: SleepSessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionStartResponse:
    device = db.scalar(select(Device).where(Device.device_code == request.device_code))
    if device is None:
        device = Device(
            device_code=request.device_code,
            hardware_revision=request.hardware_revision,
            firmware_version=request.firmware_version,
        )
        db.add(device)
        db.flush()
    else:
        if request.hardware_revision is not None:
            device.hardware_revision = request.hardware_revision
        if request.firmware_version is not None:
            device.firmware_version = request.firmware_version

    sleep_session = SleepSession(
        user_id=current_user.id,
        device_id=device.id,
        started_at=request.started_at or datetime.now(timezone.utc),
        model_version=request.model_version,
        app_version=request.app_version,
        firmware_version=request.firmware_version,
        os_type=request.os_type,
        os_version=request.os_version,
        ppg_sampling_rate_hz=request.ppg_sampling_rate_hz,
        acc_sampling_rate_hz=request.acc_sampling_rate_hz,
        temp_sampling_rate_hz=request.temp_sampling_rate_hz,
        session_status="recording",
        upload_status="pending",
    )
    db.add(sleep_session)
    db.commit()
    db.refresh(sleep_session)

    logger.info(
        "sleep_session.started",
        extra={
            "user_id": current_user.id,
            "device_id": sleep_session.device_id,
            "sleep_session_id": sleep_session.id,
        },
    )

    return SleepSessionStartResponse(
        session_id=sleep_session.id,
        user_id=sleep_session.user_id,
        device_id=sleep_session.device_id,
        started_at=sleep_session.started_at,
        session_status=sleep_session.session_status,
        upload_status=sleep_session.upload_status,
    )


@router.patch(
    "/{session_id}/finish",
    response_model=SleepSessionFinishResponse,
)
def finish_sleep_session(
    session_id: uuid.UUID,
    request: SleepSessionFinishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionFinishResponse:
    sleep_session = get_owned_sleep_session(db, session_id, current_user)

    if sleep_session.session_status == "aborted":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "SLEEP_SESSION_ABORTED",
            "Aborted sleep session cannot be finished",
        )

    if sleep_session.ended_at is None:
        ended_at = request.ended_at or datetime.now(timezone.utc)
        started_at = sleep_session.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=timezone.utc)

        duration_sec = int((ended_at - started_at).total_seconds())
        if duration_sec < 0:
            raise_app_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_SESSION_TIME_RANGE",
                "ended_at must be after started_at",
            )

        sleep_session.ended_at = ended_at
        sleep_session.duration_sec = duration_sec
        sleep_session.session_status = "completed"
        db.commit()
        db.refresh(sleep_session)

        logger.info(
            "sleep_session.completed",
            extra={
                "user_id": current_user.id,
                "sleep_session_id": sleep_session.id,
                "duration_sec": sleep_session.duration_sec,
                "upload_status": sleep_session.upload_status,
            },
        )

    return SleepSessionFinishResponse(
        session_id=sleep_session.id,
        user_id=sleep_session.user_id,
        device_id=sleep_session.device_id,
        started_at=sleep_session.started_at,
        ended_at=sleep_session.ended_at,
        duration_sec=sleep_session.duration_sec,
        session_status=sleep_session.session_status,
        upload_status=sleep_session.upload_status,
    )


@router.patch(
    "/{session_id}/abort",
    response_model=SleepSessionAbortResponse,
)
def abort_sleep_session(
    session_id: uuid.UUID,
    request: SleepSessionAbortRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionAbortResponse:
    sleep_session = get_owned_sleep_session(db, session_id, current_user)

    if sleep_session.session_status == "completed":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "SLEEP_SESSION_ALREADY_COMPLETED",
            "Completed sleep session cannot be aborted",
        )

    if sleep_session.ended_at is None:
        ended_at = request.ended_at or datetime.now(timezone.utc)
        started_at = sleep_session.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=timezone.utc)

        duration_sec = int((ended_at - started_at).total_seconds())
        if duration_sec < 0:
            raise_app_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_SESSION_TIME_RANGE",
                "ended_at must be after started_at",
            )

        sleep_session.ended_at = ended_at
        sleep_session.duration_sec = duration_sec

    sleep_session.session_status = "aborted"
    db.commit()
    db.refresh(sleep_session)

    logger.info(
        "sleep_session.aborted",
        extra={
            "user_id": current_user.id,
            "sleep_session_id": sleep_session.id,
            "duration_sec": sleep_session.duration_sec,
            "upload_status": sleep_session.upload_status,
        },
    )

    return SleepSessionAbortResponse(
        session_id=sleep_session.id,
        user_id=sleep_session.user_id,
        device_id=sleep_session.device_id,
        started_at=sleep_session.started_at,
        ended_at=sleep_session.ended_at,
        duration_sec=sleep_session.duration_sec,
        session_status=sleep_session.session_status,
        upload_status=sleep_session.upload_status,
    )


@router.post(
    "/{session_id}/alarm-events",
    response_model=AlarmEventCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_alarm_event(
    session_id: uuid.UUID,
    request: AlarmEventCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlarmEventCreateResponse:
    sleep_session = get_owned_sleep_session(db, session_id, current_user)

    if sleep_session.session_status == "aborted":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "SLEEP_SESSION_ABORTED",
            "Aborted sleep session cannot accept alarm events",
        )

    alarm_event = AlarmEvent(
        sleep_session_id=sleep_session.id,
        scheduled_at=request.scheduled_at,
        triggered_at=request.triggered_at or datetime.now(timezone.utc),
        alarm_type=request.alarm_type,
        sleep_stage=request.sleep_stage,
        confidence=request.confidence,
        reason=request.reason,
    )
    db.add(alarm_event)
    db.commit()
    db.refresh(alarm_event)

    return AlarmEventCreateResponse(
        alarm_event_id=alarm_event.id,
        sleep_session_id=alarm_event.sleep_session_id,
        scheduled_at=alarm_event.scheduled_at,
        triggered_at=alarm_event.triggered_at,
        alarm_type=alarm_event.alarm_type,
        sleep_stage=alarm_event.sleep_stage,
        confidence=alarm_event.confidence,
        reason=alarm_event.reason,
    )


@router.post(
    "/{session_id}/summary",
    response_model=SleepSummarySaveResponse,
)
def save_sleep_summary(
    session_id: uuid.UUID,
    request: SleepSummarySaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSummarySaveResponse:
    sleep_session = get_owned_sleep_session(db, session_id, current_user)

    if sleep_session.session_status != "completed":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "SLEEP_SUMMARY_SESSION_NOT_COMPLETED",
            "Sleep summary can be saved only after session is completed",
        )

    sleep_summary = db.scalar(
        select(SleepSummary).where(SleepSummary.sleep_session_id == sleep_session.id)
    )
    if sleep_summary is None:
        sleep_summary = SleepSummary(sleep_session_id=sleep_session.id)
        db.add(sleep_summary)

    sleep_summary.total_sleep_sec = request.total_sleep_sec
    sleep_summary.awake_sec = request.awake_sec
    sleep_summary.rem_sec = request.rem_sec
    sleep_summary.light_sec = request.light_sec
    sleep_summary.deep_sec = request.deep_sec
    sleep_summary.sleep_score = request.sleep_score
    sleep_summary.summary_json = request.summary_json

    db.commit()
    db.refresh(sleep_summary)

    return SleepSummarySaveResponse(
        summary_id=sleep_summary.id,
        sleep_session_id=sleep_summary.sleep_session_id,
        total_sleep_sec=sleep_summary.total_sleep_sec,
        awake_sec=sleep_summary.awake_sec,
        rem_sec=sleep_summary.rem_sec,
        light_sec=sleep_summary.light_sec,
        deep_sec=sleep_summary.deep_sec,
        sleep_score=sleep_summary.sleep_score,
        summary_json=sleep_summary.summary_json,
    )


@router.post(
    "/{session_id}/upload-urls",
    response_model=SleepSessionUploadUrlResponse,
)
def create_sleep_session_upload_urls(
    session_id: uuid.UUID,
    request: SleepSessionUploadUrlRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionUploadUrlResponse:
    sleep_session = get_owned_sleep_session(db, session_id, current_user)

    if sleep_session.session_status == "aborted":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "SLEEP_SESSION_ABORTED",
            "Aborted sleep session cannot request upload URLs",
        )

    sensor_file_key = f"sleep-sessions/{session_id}/sensor.parquet"
    prediction_file_key = f"sleep-sessions/{session_id}/prediction.json"

    sleep_session.sensor_file_key = sensor_file_key
    sleep_session.prediction_file_key = prediction_file_key
    sleep_session.upload_status = "uploading"
    db.commit()
    db.refresh(sleep_session)

    settings = get_settings()
    return SleepSessionUploadUrlResponse(
        session_id=sleep_session.id,
        bucket=settings.s3_bucket_name,
        expires_in=settings.s3_upload_url_expires_sec,
        sensor_file_key=sensor_file_key,
        sensor_upload_url=create_presigned_upload_url(
            file_key=sensor_file_key,
            content_type=request.sensor_content_type,
        ),
        prediction_file_key=prediction_file_key,
        prediction_upload_url=create_presigned_upload_url(
            file_key=prediction_file_key,
            content_type=request.prediction_content_type,
        ),
    )


@router.patch(
    "/{session_id}/upload",
    response_model=SleepSessionUploadUpdateResponse,
)
def update_sleep_session_upload(
    session_id: uuid.UUID,
    request: SleepSessionUploadUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionUploadUpdateResponse:
    sleep_session = get_owned_sleep_session(db, session_id, current_user)

    if request.sensor_file_key is not None:
        sleep_session.sensor_file_key = request.sensor_file_key
    if request.prediction_file_key is not None:
        sleep_session.prediction_file_key = request.prediction_file_key

    if request.upload_status == "completed":
        has_sensor_file = sleep_session.sensor_file_key is not None
        has_prediction_file = sleep_session.prediction_file_key is not None
        if not has_sensor_file or not has_prediction_file:
            raise_app_error(
                status.HTTP_400_BAD_REQUEST,
                "UPLOAD_FILES_REQUIRED",
                (
                    "sensor_file_key and prediction_file_key are required "
                    "when upload_status is completed"
                ),
            )

    sleep_session.upload_status = request.upload_status
    db.commit()
    db.refresh(sleep_session)

    return SleepSessionUploadUpdateResponse(
        session_id=sleep_session.id,
        sensor_file_key=sleep_session.sensor_file_key,
        prediction_file_key=sleep_session.prediction_file_key,
        session_status=sleep_session.session_status,
        upload_status=sleep_session.upload_status,
    )


@router.get(
    "/{session_id}",
    response_model=SleepSessionDetailResponse,
)
def get_sleep_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionDetailResponse:
    sleep_session = get_owned_sleep_session(db, session_id, current_user)

    sleep_summary = db.scalar(
        select(SleepSummary).where(SleepSummary.sleep_session_id == sleep_session.id)
    )
    alarm_events = db.scalars(
        select(AlarmEvent)
        .where(AlarmEvent.sleep_session_id == sleep_session.id)
        .order_by(AlarmEvent.triggered_at)
    ).all()

    summary = None
    if sleep_summary is not None:
        summary = SleepSummaryRead(
            summary_id=sleep_summary.id,
            total_sleep_sec=sleep_summary.total_sleep_sec,
            awake_sec=sleep_summary.awake_sec,
            rem_sec=sleep_summary.rem_sec,
            light_sec=sleep_summary.light_sec,
            deep_sec=sleep_summary.deep_sec,
            sleep_score=sleep_summary.sleep_score,
            summary_json=sleep_summary.summary_json,
        )

    return SleepSessionDetailResponse(
        session_id=sleep_session.id,
        user_id=sleep_session.user_id,
        device_id=sleep_session.device_id,
        started_at=sleep_session.started_at,
        ended_at=sleep_session.ended_at,
        duration_sec=sleep_session.duration_sec,
        model_version=sleep_session.model_version,
        app_version=sleep_session.app_version,
        firmware_version=sleep_session.firmware_version,
        os_type=sleep_session.os_type,
        os_version=sleep_session.os_version,
        ppg_sampling_rate_hz=sleep_session.ppg_sampling_rate_hz,
        acc_sampling_rate_hz=sleep_session.acc_sampling_rate_hz,
        temp_sampling_rate_hz=sleep_session.temp_sampling_rate_hz,
        sensor_file_key=sleep_session.sensor_file_key,
        prediction_file_key=sleep_session.prediction_file_key,
        session_status=sleep_session.session_status,
        upload_status=sleep_session.upload_status,
        summary=summary,
        alarm_events=[
            AlarmEventRead(
                alarm_event_id=alarm_event.id,
                scheduled_at=alarm_event.scheduled_at,
                triggered_at=alarm_event.triggered_at,
                alarm_type=alarm_event.alarm_type,
                sleep_stage=alarm_event.sleep_stage,
                confidence=alarm_event.confidence,
                reason=alarm_event.reason,
            )
            for alarm_event in alarm_events
        ],
    )
