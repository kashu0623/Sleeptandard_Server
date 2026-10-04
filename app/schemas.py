import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


GENDER_VALUES = Literal["male", "female", "other", "prefer_not_to_say"]


class UserCreateRequest(BaseModel):
    beta_code: str = Field(min_length=1, max_length=50)
    email: str | None = Field(
        default=None,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    gender: GENDER_VALUES | None = None
    birthdate: date | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        return value or None

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("birthdate")
    @classmethod
    def birthdate_must_not_be_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("birthdate cannot be in the future")
        return value


class UserResponse(BaseModel):
    user_id: uuid.UUID
    beta_code: str | None
    email: str | None
    nickname: str | None
    gender: str | None
    birthdate: date | None
    created_at: datetime
    updated_at: datetime


class AuthSignupRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=50)
    gender: GENDER_VALUES | None = None
    birthdate: date | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        return value.strip()

    @field_validator("birthdate")
    @classmethod
    def birthdate_must_not_be_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("birthdate cannot be in the future")
        return value


class AuthLoginRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthUserResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    nickname: str
    gender: str | None
    birthdate: date | None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserResponse


class DeviceCreateRequest(BaseModel):
    device_code: str = Field(min_length=1, max_length=50)
    hardware_revision: str | None = Field(default=None, max_length=50)
    firmware_version: str | None = Field(default=None, max_length=50)


class DeviceResponse(BaseModel):
    device_id: uuid.UUID
    device_code: str
    hardware_revision: str | None
    firmware_version: str | None
    created_at: datetime
    updated_at: datetime


class SleepSessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_code: str = Field(min_length=1, max_length=50)

    hardware_revision: str | None = Field(default=None, max_length=50)
    firmware_version: str | None = Field(default=None, max_length=50)

    model_version: str | None = Field(default=None, max_length=100)
    app_version: str | None = Field(default=None, max_length=50)
    os_type: str | None = Field(default=None, max_length=50)
    os_version: str | None = Field(default=None, max_length=50)

    ppg_sampling_rate_hz: int | None = Field(default=None, ge=1)
    acc_sampling_rate_hz: int | None = Field(default=None, ge=1)
    temp_sampling_rate_hz: int | None = Field(default=None, ge=1)

    started_at: datetime | None = None


class SleepSessionStartResponse(BaseModel):
    session_id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID
    started_at: datetime
    session_status: str
    upload_status: str


class SleepSessionFinishRequest(BaseModel):
    ended_at: datetime | None = None


class SleepSessionFinishResponse(BaseModel):
    session_id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID
    started_at: datetime
    ended_at: datetime
    duration_sec: int
    session_status: str
    upload_status: str


class SleepSessionAbortRequest(BaseModel):
    ended_at: datetime | None = None


class SleepSessionAbortResponse(BaseModel):
    session_id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID
    started_at: datetime
    ended_at: datetime
    duration_sec: int
    session_status: str
    upload_status: str


class AlarmEventCreateRequest(BaseModel):
    scheduled_at: datetime | None = None
    triggered_at: datetime | None = None
    alarm_type: str | None = Field(default="smart_alarm", max_length=50)
    sleep_stage: str | None = Field(default=None, max_length=50)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None


class AlarmEventCreateResponse(BaseModel):
    alarm_event_id: uuid.UUID
    sleep_session_id: uuid.UUID
    scheduled_at: datetime | None
    triggered_at: datetime
    alarm_type: str | None
    sleep_stage: str | None
    confidence: float | None
    reason: str | None


class SleepSummarySaveRequest(BaseModel):
    total_sleep_sec: int | None = Field(default=None, ge=0)
    awake_sec: int | None = Field(default=None, ge=0)
    rem_sec: int | None = Field(default=None, ge=0)
    light_sec: int | None = Field(default=None, ge=0)
    deep_sec: int | None = Field(default=None, ge=0)
    sleep_score: int | None = Field(default=None, ge=0, le=100)
    summary_json: dict[str, Any] | None = None


class SleepSummarySaveResponse(BaseModel):
    summary_id: uuid.UUID
    sleep_session_id: uuid.UUID
    total_sleep_sec: int | None
    awake_sec: int | None
    rem_sec: int | None
    light_sec: int | None
    deep_sec: int | None
    sleep_score: int | None
    summary_json: dict[str, Any] | None


class SleepSessionUploadUpdateRequest(BaseModel):
    sensor_file_key: str | None = None
    prediction_file_key: str | None = None
    upload_status: Literal["pending", "uploading", "completed", "failed"]


class SleepSessionUploadUrlRequest(BaseModel):
    sensor_content_type: str = Field(
        default="application/octet-stream",
        min_length=1,
        max_length=100,
    )
    prediction_content_type: str = Field(
        default="application/json",
        min_length=1,
        max_length=100,
    )


class SleepSessionUploadUrlResponse(BaseModel):
    session_id: uuid.UUID
    bucket: str
    expires_in: int
    sensor_file_key: str
    sensor_upload_url: str
    prediction_file_key: str
    prediction_upload_url: str


class SleepSessionUploadUpdateResponse(BaseModel):
    session_id: uuid.UUID
    sensor_file_key: str | None
    prediction_file_key: str | None
    session_status: str
    upload_status: str


class SleepSummaryRead(BaseModel):
    summary_id: uuid.UUID
    total_sleep_sec: int | None
    awake_sec: int | None
    rem_sec: int | None
    light_sec: int | None
    deep_sec: int | None
    sleep_score: int | None
    summary_json: dict[str, Any] | None


class AlarmEventRead(BaseModel):
    alarm_event_id: uuid.UUID
    scheduled_at: datetime | None
    triggered_at: datetime
    alarm_type: str | None
    sleep_stage: str | None
    confidence: float | None
    reason: str | None


class SleepSessionDetailResponse(BaseModel):
    session_id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    duration_sec: int | None

    model_version: str | None
    app_version: str | None
    firmware_version: str | None
    os_type: str | None
    os_version: str | None

    ppg_sampling_rate_hz: int | None
    acc_sampling_rate_hz: int | None
    temp_sampling_rate_hz: int | None

    sensor_file_key: str | None
    prediction_file_key: str | None
    session_status: str
    upload_status: str

    summary: SleepSummaryRead | None
    alarm_events: list[AlarmEventRead]


class UserSleepSessionListItem(BaseModel):
    session_id: uuid.UUID
    device_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    duration_sec: int | None
    session_status: str
    upload_status: str
    sleep_score: int | None
    total_sleep_sec: int | None


class UserSleepSessionListResponse(BaseModel):
    user_id: uuid.UUID
    total_count: int
    limit: int
    offset: int
    sleep_sessions: list[UserSleepSessionListItem]


class RawUploadInitiateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    format_version: str = Field(alias="formatVersion")
    file_name: str = Field(alias="fileName", min_length=1)
    content_type: str = Field(alias="contentType")
    size_bytes: int = Field(alias="sizeBytes", gt=0)
    record_size_bytes: int = Field(alias="recordSizeBytes", gt=0)
    record_count: int = Field(alias="recordCount", gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RawUploadInitiateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    upload_id: uuid.UUID = Field(alias="uploadId")
    object_key: str = Field(alias="objectKey")
    part_size_bytes: int = Field(alias="partSizeBytes")
    status: str


class RawUploadPartRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    part_number: int = Field(alias="partNumber")
    etag: str
    checksum_crc32c: str = Field(alias="checksumCrc32c")
    size_bytes: int = Field(alias="sizeBytes")


class RawUploadLastErrorRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    retryable: bool
    reported_at: datetime = Field(alias="reportedAt")


class RawUploadStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    upload_id: uuid.UUID = Field(alias="uploadId")
    status: str
    object_key: str = Field(alias="objectKey")
    file_name: str = Field(alias="fileName")
    size_bytes: int = Field(alias="sizeBytes")
    uploaded_bytes: int = Field(alias="uploadedBytes")
    total_parts: int = Field(alias="totalParts")
    attempt_count: int = Field(alias="attemptCount")
    last_attempt_at: datetime | None = Field(alias="lastAttemptAt")
    last_error: RawUploadLastErrorRead | None = Field(alias="lastError")
    completed_at: datetime | None = Field(alias="completedAt")
    aborted_at: datetime | None = Field(alias="abortedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    uploaded_parts: list[RawUploadPartRead] = Field(alias="uploadedParts")


class RawUploadListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: uuid.UUID = Field(alias="sessionId")
    session_upload_status: str = Field(alias="sessionUploadStatus")
    uploads: list[RawUploadStatusResponse]


class RawUploadFailureRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    error_code: str = Field(alias="errorCode", min_length=1, max_length=100)
    error_message: str = Field(alias="errorMessage", min_length=1, max_length=2000)
    retryable: bool


class RawUploadPresignPartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    part_number: int = Field(alias="partNumber", ge=1, le=10000)
    size_bytes: int = Field(alias="sizeBytes", gt=0)
    checksum_crc32c: str = Field(alias="checksumCrc32c", min_length=1)


class RawUploadPresignPartResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    part_number: int = Field(alias="partNumber")
    url: str
    expires_at: datetime = Field(alias="expiresAt")
    headers: dict[str, str]


class RawUploadCompletePart(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    part_number: int = Field(alias="partNumber", ge=1, le=10000)
    etag: str = Field(min_length=1)
    checksum_crc32c: str = Field(alias="checksumCrc32c", min_length=1)


class RawUploadCompleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    parts: list[RawUploadCompletePart] = Field(min_length=1)
    size_bytes: int = Field(alias="sizeBytes", gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RawUploadCompleteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    object_key: str = Field(alias="objectKey")
    size_bytes: int = Field(alias="sizeBytes")
