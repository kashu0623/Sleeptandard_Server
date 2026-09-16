import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.config import get_settings


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390_000
PASSWORD_SALT_BYTES = 16
PASSWORD_HASH_BYTES = 32


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
        dklen=PASSWORD_HASH_BYTES,
    )
    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            _base64url_encode(salt),
            _base64url_encode(password_hash),
        ]
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    if stored_hash is None:
        return False

    try:
        algorithm, iterations_text, salt_text, expected_hash_text = stored_hash.split("$")
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False

    salt = _base64url_decode(salt_text)
    expected_hash = _base64url_decode(expected_hash_text)
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected_hash),
    )
    return hmac.compare_digest(actual_hash, expected_hash)


def _token_signature(message: str) -> str:
    settings = get_settings()
    signature = hmac.new(
        settings.access_token_secret_key.encode("utf-8"),
        message.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(signature)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expires_minutes)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    header_text = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_text = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    message = f"{header_text}.{payload_text}"
    return f"{message}.{_token_signature(message)}"


def verify_access_token(token: str) -> uuid.UUID | None:
    try:
        header_text, payload_text, signature = token.split(".")
    except ValueError:
        return None

    message = f"{header_text}.{payload_text}"
    if not hmac.compare_digest(_token_signature(message), signature):
        return None

    try:
        payload = json.loads(_base64url_decode(payload_text))
        if payload.get("type") != "access":
            return None
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return uuid.UUID(payload["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
