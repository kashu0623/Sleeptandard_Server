import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import raise_app_error
from app.models import SleepSession, SleepSessionUpload, User
from app.schemas import (
    RawUploadCompleteRequest,
    RawUploadCompleteResponse,
    RawUploadFailureRequest,
    RawUploadInitiateRequest,
    RawUploadInitiateResponse,
    RawUploadLastErrorRead,
    RawUploadListResponse,
    RawUploadPartRead,
    RawUploadPresignPartRequest,
    RawUploadPresignPartResponse,
    RawUploadStatusResponse,
)
from app.security import get_current_user
from app.services.s3 import (
    abort_multipart_upload,
    complete_multipart_upload,
    create_multipart_upload,
    create_presigned_part_url,
    list_uploaded_parts,
    uses_local_multipart_backend,
)


router = APIRouter(prefix="/v1", tags=["raw_uploads"])
logger = logging.getLogger("sleeptandard.raw_upload")

RAW_FORMAT_VERSION = "potch-raw-v1"
RAW_CONTENT_TYPE = "application/octet-stream"
RAW_RECORD_SIZE_BYTES = 150
RAW_KIND = "RAW_SENSOR"
RAW_PART_SIZE_BYTES = 8 * 1024 * 1024
RAW_MIN_NON_FINAL_PART_SIZE_BYTES = 5 * 1024 * 1024


def _get_sleep_session(
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
            retryable=False,
        )
    if sleep_session.user_id != current_user.id:
        raise_app_error(
            status.HTTP_403_FORBIDDEN,
            "SLEEP_SESSION_FORBIDDEN",
            "You can access only your own sleep sessions",
            retryable=False,
        )
    if sleep_session.session_status == "aborted":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "SLEEP_SESSION_ABORTED",
            "Aborted sleep session cannot upload raw data",
            retryable=False,
        )
    return sleep_session


def _get_upload(
    db: Session,
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    current_user: User,
) -> SleepSessionUpload:
    _get_sleep_session(db, session_id, current_user)
    upload = db.get(SleepSessionUpload, upload_id)
    if upload is None or upload.session_id != session_id:
        raise_app_error(
            status.HTTP_404_NOT_FOUND,
            "UPLOAD_NOT_FOUND",
            "Upload not found",
            retryable=False,
        )
    return upload


def _uploaded_parts(upload: SleepSessionUpload) -> list[dict]:
    if upload.status in {"COMPLETE", "ABORTED"} or uses_local_multipart_backend():
        return sorted(upload.uploaded_parts or [], key=lambda part: part["partNumber"])
    return list_uploaded_parts(
        object_key=upload.object_key,
        s3_upload_id=upload.s3_upload_id,
    )


def _raw_upload_status_response(
    upload: SleepSessionUpload,
    uploaded_parts: list[dict] | None = None,
) -> RawUploadStatusResponse:
    parts = uploaded_parts if uploaded_parts is not None else _uploaded_parts(upload)
    part_models = [
        RawUploadPartRead(
            part_number=part["partNumber"],
            etag=part["etag"],
            checksum_crc32c=part.get("checksumCrc32c", ""),
            size_bytes=part["sizeBytes"],
        )
        for part in parts
    ]
    uploaded_bytes = (
        upload.size_bytes
        if upload.status == "COMPLETE"
        else sum(part.size_bytes for part in part_models)
    )
    total_parts = (upload.size_bytes + upload.part_size_bytes - 1) // (
        upload.part_size_bytes
    )
    last_error = None
    if (
        upload.last_error_code is not None
        and upload.last_error_message is not None
        and upload.last_error_retryable is not None
        and upload.last_error_at is not None
    ):
        last_error = RawUploadLastErrorRead(
            code=upload.last_error_code,
            message=upload.last_error_message,
            retryable=upload.last_error_retryable,
            reported_at=upload.last_error_at,
        )
    return RawUploadStatusResponse(
        upload_id=upload.id,
        status=upload.status,
        object_key=upload.object_key,
        file_name=upload.file_name,
        size_bytes=upload.size_bytes,
        uploaded_bytes=uploaded_bytes,
        total_parts=total_parts,
        attempt_count=upload.attempt_count,
        last_attempt_at=upload.last_attempt_at,
        last_error=last_error,
        completed_at=upload.completed_at,
        aborted_at=upload.aborted_at,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
        uploaded_parts=part_models,
    )


def _validate_initiate_request(
    *,
    session_id: uuid.UUID,
    request: RawUploadInitiateRequest,
) -> None:
    if request.format_version != RAW_FORMAT_VERSION:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_RAW_FORMAT_VERSION",
            "formatVersion must be potch-raw-v1",
            retryable=False,
        )
    if request.content_type != RAW_CONTENT_TYPE:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_RAW_CONTENT_TYPE",
            "contentType must be application/octet-stream",
            retryable=False,
        )
    if request.record_size_bytes != RAW_RECORD_SIZE_BYTES:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_RAW_RECORD_SIZE",
            "recordSizeBytes must be 150",
            retryable=False,
        )
    if request.size_bytes % request.record_size_bytes != 0:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_RAW_FILE_SIZE",
            "sizeBytes must be divisible by recordSizeBytes",
            retryable=False,
        )
    if request.record_count != request.size_bytes // request.record_size_bytes:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_RAW_RECORD_COUNT",
            "recordCount must match sizeBytes / recordSizeBytes",
            retryable=False,
        )
    if str(session_id) not in request.file_name:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "RAW_FILE_SESSION_MISMATCH",
            "fileName must contain the sleep session id",
            retryable=False,
        )


def _object_key(sleep_session: SleepSession, session_id: uuid.UUID) -> str:
    return (
        f"users/{sleep_session.user_id}/"
        f"sleep-sessions/{session_id}/sensor.raw.v1.bin"
    )


def _validate_part_size(
    *,
    upload: SleepSessionUpload,
    part_number: int,
    size_bytes: int,
) -> None:
    expected_total_parts = (upload.size_bytes + upload.part_size_bytes - 1) // (
        upload.part_size_bytes
    )
    if part_number > expected_total_parts:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_UPLOAD_PART",
            "partNumber is outside the expected range",
            retryable=False,
        )

    expected_offset = (part_number - 1) * upload.part_size_bytes
    expected_size = min(upload.part_size_bytes, upload.size_bytes - expected_offset)
    if size_bytes != expected_size:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_UPLOAD_PART_SIZE",
            "sizeBytes does not match the expected part size",
            retryable=False,
        )
    if (
        expected_total_parts > 1
        and part_number < expected_total_parts
        and size_bytes < RAW_MIN_NON_FINAL_PART_SIZE_BYTES
    ):
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "UPLOAD_PART_TOO_SMALL",
            "Non-final S3 multipart parts must be at least 5 MiB",
            retryable=False,
        )


def _raw_upload_response(upload: SleepSessionUpload) -> RawUploadInitiateResponse:
    return RawUploadInitiateResponse(
        upload_id=upload.id,
        object_key=upload.object_key,
        part_size_bytes=upload.part_size_bytes,
        status=upload.status,
    )


@router.post(
    "/sleep-sessions/{session_id}/raw-uploads",
    response_model=RawUploadInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
def initiate_raw_upload(
    session_id: uuid.UUID,
    request: RawUploadInitiateRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawUploadInitiateResponse:
    sleep_session = _get_sleep_session(db, session_id, current_user)
    _validate_initiate_request(session_id=session_id, request=request)

    existing_upload = db.scalar(
        select(SleepSessionUpload).where(
            SleepSessionUpload.session_id == session_id,
            SleepSessionUpload.kind == RAW_KIND,
            SleepSessionUpload.format_version == request.format_version,
            SleepSessionUpload.sha256 == request.sha256,
        )
    )
    if existing_upload is not None:
        response.status_code = status.HTTP_200_OK
        logger.info(
            "raw_upload.reused",
            extra={
                "user_id": current_user.id,
                "sleep_session_id": session_id,
                "upload_id": existing_upload.id,
                "upload_status": existing_upload.status,
                "size_bytes": existing_upload.size_bytes,
            },
        )
        return _raw_upload_response(existing_upload)

    object_key = _object_key(sleep_session, session_id)
    upload = SleepSessionUpload(
        session_id=session_id,
        kind=RAW_KIND,
        format_version=request.format_version,
        object_key=object_key,
        s3_upload_id=create_multipart_upload(
            object_key=object_key,
            content_type=request.content_type,
        ),
        file_name=request.file_name,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
        record_size_bytes=request.record_size_bytes,
        record_count=request.record_count,
        sha256=request.sha256,
        part_size_bytes=RAW_PART_SIZE_BYTES,
        status="UPLOADING",
        uploaded_parts=[],
    )
    sleep_session.upload_status = "uploading"
    db.add(upload)
    db.commit()
    db.refresh(upload)
    logger.info(
        "raw_upload.initiated",
        extra={
            "user_id": current_user.id,
            "sleep_session_id": session_id,
            "upload_id": upload.id,
            "upload_status": upload.status,
            "size_bytes": upload.size_bytes,
        },
    )
    return _raw_upload_response(upload)


@router.get(
    "/sleep-sessions/{session_id}/raw-uploads",
    response_model=RawUploadListResponse,
)
def list_raw_uploads(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawUploadListResponse:
    sleep_session = _get_sleep_session(db, session_id, current_user)
    uploads = db.scalars(
        select(SleepSessionUpload)
        .where(SleepSessionUpload.session_id == session_id)
        .order_by(SleepSessionUpload.created_at.desc())
    ).all()
    return RawUploadListResponse(
        session_id=session_id,
        session_upload_status=sleep_session.upload_status,
        uploads=[_raw_upload_status_response(upload) for upload in uploads],
    )


@router.get(
    "/sleep-sessions/{session_id}/raw-uploads/{upload_id}",
    response_model=RawUploadStatusResponse,
)
def get_raw_upload_status(
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawUploadStatusResponse:
    upload = _get_upload(db, session_id, upload_id, current_user)
    return _raw_upload_status_response(upload)


@router.post(
    "/sleep-sessions/{session_id}/raw-uploads/{upload_id}/attempts",
    response_model=RawUploadStatusResponse,
)
def report_raw_upload_attempt(
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawUploadStatusResponse:
    upload = _get_upload(db, session_id, upload_id, current_user)
    if upload.status == "ABORTED":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "UPLOAD_NOT_ACTIVE",
            "Upload is not active",
            retryable=False,
        )
    if upload.status != "COMPLETE":
        upload.status = "UPLOADING"
        upload.attempt_count += 1
        upload.last_attempt_at = datetime.now(timezone.utc)
        sleep_session = db.get(SleepSession, session_id)
        if sleep_session is not None:
            sleep_session.upload_status = "uploading"
        db.commit()
        db.refresh(upload)
        logger.info(
            "raw_upload.attempted",
            extra={
                "user_id": current_user.id,
                "sleep_session_id": session_id,
                "upload_id": upload.id,
                "upload_status": upload.status,
                "attempt_count": upload.attempt_count,
            },
        )
    return _raw_upload_status_response(upload)


@router.post(
    "/sleep-sessions/{session_id}/raw-uploads/{upload_id}/failure",
    response_model=RawUploadStatusResponse,
)
def report_raw_upload_failure(
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: RawUploadFailureRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawUploadStatusResponse:
    upload = _get_upload(db, session_id, upload_id, current_user)
    if upload.status == "COMPLETE":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "UPLOAD_ALREADY_COMPLETE",
            "Completed upload cannot be marked as failed",
            retryable=False,
        )
    if upload.status == "ABORTED":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "UPLOAD_NOT_ACTIVE",
            "Upload is not active",
            retryable=False,
        )

    now = datetime.now(timezone.utc)
    upload.status = "FAILED"
    upload.last_error_code = request.error_code
    upload.last_error_message = request.error_message
    upload.last_error_retryable = request.retryable
    upload.last_error_at = now
    sleep_session = db.get(SleepSession, session_id)
    if sleep_session is not None:
        sleep_session.upload_status = "failed"
    db.commit()
    db.refresh(upload)
    logger.warning(
        "raw_upload.failed",
        extra={
            "user_id": current_user.id,
            "sleep_session_id": session_id,
            "upload_id": upload.id,
            "upload_status": upload.status,
            "attempt_count": upload.attempt_count,
            "error_code": request.error_code,
            "retryable": request.retryable,
        },
    )
    return _raw_upload_status_response(upload)


@router.post(
    "/sleep-sessions/{session_id}/raw-uploads/{upload_id}/parts/presign",
    response_model=RawUploadPresignPartResponse,
)
def presign_raw_upload_part(
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: RawUploadPresignPartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawUploadPresignPartResponse:
    upload = _get_upload(db, session_id, upload_id, current_user)
    if upload.status != "UPLOADING":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "UPLOAD_NOT_ACTIVE",
            "Upload is not active",
            retryable=False,
        )
    _validate_part_size(
        upload=upload,
        part_number=request.part_number,
        size_bytes=request.size_bytes,
    )

    settings = get_settings()
    return RawUploadPresignPartResponse(
        part_number=request.part_number,
        url=create_presigned_part_url(
            object_key=upload.object_key,
            s3_upload_id=upload.s3_upload_id,
            part_number=request.part_number,
            checksum_crc32c=request.checksum_crc32c,
            upload_id=str(upload.id),
        ),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.s3_upload_url_expires_sec),
        headers={"x-amz-checksum-crc32c": request.checksum_crc32c},
    )


@router.post(
    "/sleep-sessions/{session_id}/raw-uploads/{upload_id}/complete",
    response_model=RawUploadCompleteResponse,
)
def complete_raw_upload(
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: RawUploadCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawUploadCompleteResponse:
    upload = _get_upload(db, session_id, upload_id, current_user)
    if upload.status == "COMPLETE":
        return RawUploadCompleteResponse(
            status=upload.status,
            object_key=upload.object_key,
            size_bytes=upload.size_bytes,
        )
    if upload.status != "UPLOADING":
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "UPLOAD_NOT_ACTIVE",
            "Upload is not active",
            retryable=False,
        )
    if request.size_bytes != upload.size_bytes or request.sha256 != upload.sha256:
        raise_app_error(
            status.HTTP_409_CONFLICT,
            "UPLOAD_FILE_MISMATCH",
            "Completed upload metadata does not match the initiated file",
            retryable=False,
        )

    parts = [part.model_dump(by_alias=True) for part in request.parts]
    expected_numbers = list(range(1, len(parts) + 1))
    actual_numbers = [part["partNumber"] for part in parts]
    if actual_numbers != expected_numbers:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_UPLOAD_PARTS",
            "parts must be consecutive and start at 1",
            retryable=False,
        )

    uploaded_parts = _uploaded_parts(upload)
    uploaded_by_number = {part["partNumber"]: part for part in uploaded_parts}
    for part in parts:
        uploaded = uploaded_by_number.get(part["partNumber"])
        if uploaded is None:
            raise_app_error(
                status.HTTP_409_CONFLICT,
                "UPLOAD_PART_MISSING",
                "At least one uploaded part is missing",
                retryable=True,
            )
        if uploaded["etag"] != part["etag"]:
            raise_app_error(
                status.HTTP_409_CONFLICT,
                "UPLOAD_PART_ETAG_MISMATCH",
                "Uploaded part ETag does not match",
                retryable=False,
            )

    complete_multipart_upload(
        object_key=upload.object_key,
        s3_upload_id=upload.s3_upload_id,
        parts=parts,
    )
    upload.status = "COMPLETE"
    upload.completed_at = datetime.now(timezone.utc)
    sleep_session = _get_sleep_session(db, session_id, current_user)
    sleep_session.sensor_file_key = upload.object_key
    sleep_session.upload_status = "completed"
    db.commit()
    db.refresh(upload)

    logger.info(
        "raw_upload.completed",
        extra={
            "user_id": current_user.id,
            "sleep_session_id": session_id,
            "upload_id": upload.id,
            "upload_status": upload.status,
            "attempt_count": upload.attempt_count,
            "size_bytes": upload.size_bytes,
            "uploaded_bytes": upload.size_bytes,
        },
    )

    return RawUploadCompleteResponse(
        status=upload.status,
        object_key=upload.object_key,
        size_bytes=upload.size_bytes,
    )


@router.delete(
    "/sleep-sessions/{session_id}/raw-uploads/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def abort_raw_upload(
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    upload = _get_upload(db, session_id, upload_id, current_user)
    if upload.status in {"UPLOADING", "FAILED"}:
        abort_multipart_upload(
            object_key=upload.object_key,
            s3_upload_id=upload.s3_upload_id,
        )
        upload.status = "ABORTED"
        upload.aborted_at = datetime.now(timezone.utc)
        sleep_session = db.get(SleepSession, session_id)
        if sleep_session is not None:
            sleep_session.upload_status = "failed"
        db.commit()
        logger.info(
            "raw_upload.aborted",
            extra={
                "user_id": current_user.id,
                "sleep_session_id": session_id,
                "upload_id": upload.id,
                "upload_status": upload.status,
                "attempt_count": upload.attempt_count,
            },
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/local-s3/raw-uploads/{upload_id}/parts/{part_number}",
    include_in_schema=False,
)
async def upload_local_raw_part(
    upload_id: uuid.UUID,
    part_number: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    if not uses_local_multipart_backend():
        raise_app_error(
            status.HTTP_404_NOT_FOUND,
            "LOCAL_S3_NOT_ENABLED",
            "Local S3 upload endpoint is not enabled",
        )

    upload = db.get(SleepSessionUpload, upload_id)
    if upload is None:
        raise_app_error(
            status.HTTP_404_NOT_FOUND,
            "UPLOAD_NOT_FOUND",
            "Upload not found",
            retryable=False,
        )
    checksum_crc32c = request.headers.get("x-amz-checksum-crc32c")
    if not checksum_crc32c:
        raise_app_error(
            status.HTTP_400_BAD_REQUEST,
            "UPLOAD_CHECKSUM_REQUIRED",
            "x-amz-checksum-crc32c header is required",
            retryable=False,
        )

    body = await request.body()
    _validate_part_size(
        upload=upload,
        part_number=part_number,
        size_bytes=len(body),
    )
    etag = f"\"{hashlib.md5(body, usedforsecurity=False).hexdigest()}\""
    existing_parts = upload.uploaded_parts or []
    next_parts = [
        part for part in existing_parts if part["partNumber"] != part_number
    ]
    next_parts.append(
        {
            "partNumber": part_number,
            "etag": etag,
            "checksumCrc32c": checksum_crc32c,
            "sizeBytes": len(body),
        }
    )
    upload.uploaded_parts = sorted(next_parts, key=lambda part: part["partNumber"])
    db.commit()

    return Response(status_code=status.HTTP_200_OK, headers={"ETag": etag})
