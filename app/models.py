import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    BigInteger,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    beta_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    nickname: Mapped[str | None] = mapped_column(String(50))
    gender: Mapped[str | None] = mapped_column(String(20))
    birthdate: Mapped[date | None] = mapped_column(Date)

    sleep_sessions: Mapped[list["SleepSession"]] = relationship(back_populates="user")


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hardware_revision: Mapped[str | None] = mapped_column(String(50))
    firmware_version: Mapped[str | None] = mapped_column(String(50))

    sleep_sessions: Mapped[list["SleepSession"]] = relationship(back_populates="device")


class SleepSession(TimestampMixin, Base):
    __tablename__ = "sleep_sessions"
    __table_args__ = (
        CheckConstraint(
            "session_status IN ('recording', 'completed', 'aborted')",
            name="ck_sleep_sessions_session_status",
        ),
        CheckConstraint(
            "upload_status IN ('pending', 'uploading', 'completed', 'failed')",
            name="ck_sleep_sessions_upload_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False, index=True
    )

    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    duration_sec: Mapped[int | None] = mapped_column(Integer)

    model_version: Mapped[str | None] = mapped_column(String(100))
    app_version: Mapped[str | None] = mapped_column(String(50))
    firmware_version: Mapped[str | None] = mapped_column(String(50))

    os_type: Mapped[str | None] = mapped_column(String(50))
    os_version: Mapped[str | None] = mapped_column(String(50))

    ppg_sampling_rate_hz: Mapped[int | None] = mapped_column(Integer)
    acc_sampling_rate_hz: Mapped[int | None] = mapped_column(Integer)
    temp_sampling_rate_hz: Mapped[int | None] = mapped_column(Integer)

    sensor_file_key: Mapped[str | None] = mapped_column(Text)
    prediction_file_key: Mapped[str | None] = mapped_column(Text)

    session_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="recording"
    )
    upload_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )

    user: Mapped[User] = relationship(back_populates="sleep_sessions")
    device: Mapped[Device] = relationship(back_populates="sleep_sessions")
    summary: Mapped["SleepSummary | None"] = relationship(
        back_populates="sleep_session", cascade="all, delete-orphan"
    )
    alarm_events: Mapped[list["AlarmEvent"]] = relationship(
        back_populates="sleep_session", cascade="all, delete-orphan"
    )
    uploads: Mapped[list["SleepSessionUpload"]] = relationship(
        back_populates="sleep_session", cascade="all, delete-orphan"
    )


class SleepSessionUpload(TimestampMixin, Base):
    __tablename__ = "sleep_session_uploads"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('RAW_SENSOR')",
            name="ck_sleep_session_uploads_kind",
        ),
        CheckConstraint(
            "status IN ('UPLOADING', 'COMPLETE', 'ABORTED', 'FAILED')",
            name="ck_sleep_session_uploads_status",
        ),
        CheckConstraint("size_bytes > 0", name="ck_sleep_session_uploads_size"),
        CheckConstraint("record_size_bytes > 0", name="ck_sleep_session_uploads_record_size"),
        CheckConstraint("record_count > 0", name="ck_sleep_session_uploads_record_count"),
        UniqueConstraint(
            "session_id",
            "kind",
            "format_version",
            "sha256",
            name="uq_sleep_session_uploads_file_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sleep_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    format_version: Mapped[str] = mapped_column(String(30), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    s3_upload_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    record_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    part_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    uploaded_parts: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    sleep_session: Mapped[SleepSession] = relationship(back_populates="uploads")


class SleepSummary(TimestampMixin, Base):
    __tablename__ = "sleep_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sleep_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sleep_sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    total_sleep_sec: Mapped[int | None] = mapped_column(Integer)
    awake_sec: Mapped[int | None] = mapped_column(Integer)
    rem_sec: Mapped[int | None] = mapped_column(Integer)
    light_sec: Mapped[int | None] = mapped_column(Integer)
    deep_sec: Mapped[int | None] = mapped_column(Integer)
    sleep_score: Mapped[int | None] = mapped_column(Integer)
    summary_json: Mapped[dict | None] = mapped_column(JSONB)

    sleep_session: Mapped[SleepSession] = relationship(back_populates="summary")


class AlarmEvent(TimestampMixin, Base):
    __tablename__ = "alarm_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sleep_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sleep_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scheduled_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    triggered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    alarm_type: Mapped[str | None] = mapped_column(String(50))
    sleep_stage: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)

    sleep_session: Mapped[SleepSession] = relationship(back_populates="alarm_events")
