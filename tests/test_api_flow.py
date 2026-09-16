import uuid
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
AUTH_HEADERS = {"X-API-Key": "local-dev-api-key"}


def create_auth_headers() -> tuple[dict[str, str], str]:
    email = f"test-auth-{uuid.uuid4().hex}@example.com"
    signup_response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "correct-password-123",
            "nickname": "Test User",
        },
    )
    assert signup_response.status_code == 201
    signup = signup_response.json()
    return {"Authorization": f"Bearer {signup['access_token']}"}, signup["user"]["user_id"]


def test_health_and_db_health() -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    db_response = client.get("/health/db")
    assert db_response.status_code == 200
    assert db_response.json() == {"status": "ok", "db": 1}


def test_protected_apis_require_api_key() -> None:
    missing_key_response = client.post("/users/", json={"beta_code": "TEST_BETA_AUTH"})
    assert missing_key_response.status_code == 401
    assert missing_key_response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "X-API-Key or Authorization bearer token is required",
    }

    invalid_key_response = client.post(
        "/users/",
        headers={"X-API-Key": "wrong-key"},
        json={"beta_code": "TEST_BETA_AUTH"},
    )
    assert invalid_key_response.status_code == 403
    assert invalid_key_response.json() == {
        "code": "INVALID_API_KEY",
        "message": "Invalid API key",
    }

    bearer_response = client.get(
        "/users/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer local-dev-api-key"},
    )
    assert bearer_response.status_code == 401
    assert bearer_response.json()["code"] == "INVALID_ACCESS_TOKEN"


def test_auth_signup_login_and_me_flow() -> None:
    email = f"test-auth-{uuid.uuid4().hex}@example.com"
    password = "correct-password-123"

    signup_response = client.post(
        "/auth/signup",
        json={
            "email": email.upper(),
            "password": password,
            "nickname": "Auth Tester",
            "gender": "other",
            "birthdate": "1992-07-09",
        },
    )
    assert signup_response.status_code == 201
    signup = signup_response.json()
    assert signup["token_type"] == "bearer"
    assert signup["access_token"]
    assert signup["expires_in"] == 604800
    assert signup["user"]["email"] == email
    assert signup["user"]["nickname"] == "Auth Tester"
    assert signup["user"]["gender"] == "other"
    assert signup["user"]["birthdate"] == "1992-07-09"
    assert "password" not in signup
    assert "password_hash" not in signup["user"]

    duplicate_response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "another-password-123",
            "nickname": "Duplicate",
        },
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "code": "EMAIL_ALREADY_EXISTS",
        "message": "Email already exists",
    }

    bad_login_response = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password"},
    )
    assert bad_login_response.status_code == 401
    assert bad_login_response.json() == {
        "code": "INVALID_LOGIN_CREDENTIALS",
        "message": "Invalid email or password",
    }

    login_response = client.post(
        "/auth/login",
        json={"email": email.upper(), "password": password},
    )
    assert login_response.status_code == 200
    login = login_response.json()
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}

    me_response = client.get("/auth/me", headers=auth_headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == email

    protected_response = client.get(
        f"/users/{login['user']['user_id']}",
        headers=auth_headers,
    )
    assert protected_response.status_code == 200
    assert protected_response.json()["email"] == email


def test_user_and_device_registration_are_reusable() -> None:
    beta_code = f"TEST_BETA_{uuid.uuid4().hex}"
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"
    email = f"test-{uuid.uuid4().hex}@example.com"

    user_response = client.post(
        "/users/",
        headers=AUTH_HEADERS,
        json={
            "beta_code": beta_code,
            "email": email,
            "nickname": "tester",
            "gender": "prefer_not_to_say",
            "birthdate": "1995-03-14",
        },
    )
    assert user_response.status_code == 201
    user = user_response.json()
    assert user["beta_code"] == beta_code
    assert user["email"] == email
    assert user["nickname"] == "tester"
    assert user["gender"] == "prefer_not_to_say"
    assert user["birthdate"] == "1995-03-14"

    same_user_response = client.post(
        "/users/",
        headers=AUTH_HEADERS,
        json={"beta_code": beta_code},
    )
    assert same_user_response.status_code == 200
    assert same_user_response.json()["user_id"] == user["user_id"]

    duplicate_email_response = client.post(
        "/users/",
        headers=AUTH_HEADERS,
        json={
            "beta_code": f"TEST_BETA_{uuid.uuid4().hex}",
            "email": email,
            "nickname": "other tester",
        },
    )
    assert duplicate_email_response.status_code == 409
    assert duplicate_email_response.json() == {
        "code": "EMAIL_ALREADY_EXISTS",
        "message": "Email already exists",
    }

    device_response = client.post(
        "/devices/",
        headers=AUTH_HEADERS,
        json={
            "device_code": device_code,
            "hardware_revision": "HW_REV_A",
            "firmware_version": "0.8.1",
        },
    )
    assert device_response.status_code == 201
    device = device_response.json()
    assert device["device_code"] == device_code

    same_device_response = client.post(
        "/devices/",
        headers=AUTH_HEADERS,
        json={
            "device_code": device_code,
            "hardware_revision": "HW_REV_A",
            "firmware_version": "0.8.2",
        },
    )
    assert same_device_response.status_code == 200
    same_device = same_device_response.json()
    assert same_device["device_id"] == device["device_id"]
    assert same_device["firmware_version"] == "0.8.2"

    get_device_response = client.get(
        f"/devices/{device['device_id']}",
        headers=AUTH_HEADERS,
    )
    assert get_device_response.status_code == 200
    assert get_device_response.json()["device_code"] == device_code


def test_sleep_session_full_success_flow() -> None:
    auth_headers, user_id = create_auth_headers()
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"

    start_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "device_code": device_code,
            "hardware_revision": "HW_REV_A",
            "firmware_version": "0.8.1",
            "model_version": "sleep_4class_v1.0",
            "app_version": "0.9.0",
            "os_type": "ios",
            "os_version": "18.0",
            "ppg_sampling_rate_hz": 100,
            "acc_sampling_rate_hz": 100,
            "temp_sampling_rate_hz": 1,
            "started_at": "2026-09-05T15:00:00Z",
        },
    )
    assert start_response.status_code == 201
    started_session = start_response.json()
    session_id = started_session["session_id"]
    assert started_session["user_id"] == user_id
    assert started_session["session_status"] == "recording"
    assert started_session["upload_status"] == "pending"

    alarm_response = client.post(
        f"/sleep-sessions/{session_id}/alarm-events",
        headers=auth_headers,
        json={
            "scheduled_at": "2026-09-05T22:55:00Z",
            "triggered_at": "2026-09-05T22:50:00Z",
            "alarm_type": "smart_alarm",
            "sleep_stage": "light",
            "confidence": 0.87,
            "reason": "Light sleep detected inside alarm window",
        },
    )
    assert alarm_response.status_code == 201
    assert alarm_response.json()["sleep_session_id"] == session_id

    finish_response = client.patch(
        f"/sleep-sessions/{session_id}/finish",
        headers=auth_headers,
        json={"ended_at": "2026-09-05T23:00:00Z"},
    )
    assert finish_response.status_code == 200
    finished_session = finish_response.json()
    assert finished_session["duration_sec"] == 28800
    assert finished_session["session_status"] == "completed"

    summary_response = client.post(
        f"/sleep-sessions/{session_id}/summary",
        headers=auth_headers,
        json={
            "total_sleep_sec": 25200,
            "awake_sec": 1800,
            "rem_sec": 5400,
            "light_sec": 12600,
            "deep_sec": 7200,
            "sleep_score": 86,
            "summary_json": {
                "note": "Good sleep continuity",
                "stage_model": "sleep_4class_v1.0",
            },
        },
    )
    assert summary_response.status_code == 200
    assert summary_response.json()["sleep_score"] == 86

    upload_url_response = client.post(
        f"/sleep-sessions/{session_id}/upload-urls",
        headers=auth_headers,
        json={
            "sensor_content_type": "application/octet-stream",
            "prediction_content_type": "application/json",
        },
    )
    assert upload_url_response.status_code == 200
    upload_urls = upload_url_response.json()
    assert upload_urls["session_id"] == session_id
    assert upload_urls["bucket"] == "wearable-sleep-local"
    assert upload_urls["expires_in"] == 900
    assert upload_urls["sensor_file_key"] == f"sleep-sessions/{session_id}/sensor.parquet"
    assert upload_urls["prediction_file_key"] == (
        f"sleep-sessions/{session_id}/prediction.json"
    )
    assert upload_urls["sensor_upload_url"].startswith("https://")
    assert upload_urls["prediction_upload_url"].startswith("https://")

    upload_response = client.patch(
        f"/sleep-sessions/{session_id}/upload",
        headers=auth_headers,
        json={
            "sensor_file_key": upload_urls["sensor_file_key"],
            "prediction_file_key": upload_urls["prediction_file_key"],
            "upload_status": "completed",
        },
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["upload_status"] == "completed"

    detail_response = client.get(
        f"/sleep-sessions/{session_id}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["session_status"] == "completed"
    assert detail["upload_status"] == "completed"
    assert detail["summary"]["sleep_score"] == 86
    assert len(detail["alarm_events"]) == 1

    list_response = client.get(
        f"/users/{user_id}/sleep-sessions",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    sleep_sessions = list_response.json()["sleep_sessions"]
    assert len(sleep_sessions) == 1
    assert sleep_sessions[0]["session_id"] == session_id
    assert sleep_sessions[0]["sleep_score"] == 86


def test_sleep_session_start_uses_token_user_and_rejects_client_user_fields() -> None:
    auth_headers, user_id = create_auth_headers()
    other_user_id = uuid.uuid4()
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"

    start_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "device_code": device_code,
            "started_at": "2026-09-05T15:00:00Z",
        },
    )
    assert start_response.status_code == 201
    assert start_response.json()["user_id"] == user_id

    user_id_in_body_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "user_id": str(other_user_id),
            "device_code": f"TEST_DEV_{uuid.uuid4().hex}",
        },
    )
    assert user_id_in_body_response.status_code == 422
    assert user_id_in_body_response.json()["code"] == "VALIDATION_ERROR"

    beta_code_in_body_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "beta_code": f"TEST_BETA_{uuid.uuid4().hex}",
            "device_code": f"TEST_DEV_{uuid.uuid4().hex}",
        },
    )
    assert beta_code_in_body_response.status_code == 422
    assert beta_code_in_body_response.json()["code"] == "VALIDATION_ERROR"


def test_sleep_session_abort_flow() -> None:
    auth_headers, _ = create_auth_headers()
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"

    start_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "device_code": device_code,
            "started_at": "2026-09-05T15:00:00Z",
        },
    )
    assert start_response.status_code == 201
    session_id = start_response.json()["session_id"]

    abort_response = client.patch(
        f"/sleep-sessions/{session_id}/abort",
        headers=auth_headers,
        json={"ended_at": "2026-09-05T16:30:00Z"},
    )
    assert abort_response.status_code == 200
    aborted_session = abort_response.json()
    assert aborted_session["duration_sec"] == 5400
    assert aborted_session["session_status"] == "aborted"

    summary_response = client.post(
        f"/sleep-sessions/{session_id}/summary",
        headers=auth_headers,
        json={"sleep_score": 10},
    )
    assert summary_response.status_code == 409
    assert summary_response.json() == {
        "code": "SLEEP_SUMMARY_SESSION_NOT_COMPLETED",
        "message": "Sleep summary can be saved only after session is completed",
    }

    upload_url_response = client.post(
        f"/sleep-sessions/{session_id}/upload-urls",
        headers=auth_headers,
        json={},
    )
    assert upload_url_response.status_code == 409
    assert upload_url_response.json() == {
        "code": "SLEEP_SESSION_ABORTED",
        "message": "Aborted sleep session cannot request upload URLs",
    }


def test_sleep_session_rejects_other_user_token() -> None:
    owner_headers, _ = create_auth_headers()
    other_headers, _ = create_auth_headers()
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"

    start_response = client.post(
        "/sleep-sessions/start",
        headers=owner_headers,
        json={
            "device_code": device_code,
            "started_at": "2026-09-05T15:00:00Z",
        },
    )
    assert start_response.status_code == 201
    session_id = start_response.json()["session_id"]

    detail_response = client.get(
        f"/sleep-sessions/{session_id}",
        headers=other_headers,
    )
    assert detail_response.status_code == 403
    assert detail_response.json() == {
        "code": "SLEEP_SESSION_FORBIDDEN",
        "message": "You can access only your own sleep sessions",
    }

    raw_upload_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads",
        headers=other_headers,
        json={
            "formatVersion": "potch-raw-v1",
            "fileName": f"potch_packet_raw_data_20260911_183104_123_{session_id}.bin",
            "contentType": "application/octet-stream",
            "sizeBytes": 150,
            "recordSizeBytes": 150,
            "recordCount": 1,
            "sha256": "b" * 64,
        },
    )
    assert raw_upload_response.status_code == 403
    assert raw_upload_response.json()["code"] == "SLEEP_SESSION_FORBIDDEN"


def test_error_responses_have_consistent_shape() -> None:
    auth_headers, _ = create_auth_headers()
    missing_session_id = uuid.uuid4()
    missing_user_id = uuid.uuid4()
    missing_device_id = uuid.uuid4()

    missing_session_response = client.get(
        f"/sleep-sessions/{missing_session_id}",
        headers=auth_headers,
    )
    assert missing_session_response.status_code == 404
    assert missing_session_response.json() == {
        "code": "SLEEP_SESSION_NOT_FOUND",
        "message": "Sleep session not found",
    }

    missing_user_response = client.get(
        f"/users/{missing_user_id}",
        headers=auth_headers,
    )
    assert missing_user_response.status_code == 403
    assert missing_user_response.json() == {
        "code": "USER_FORBIDDEN",
        "message": "You can access only your own user data",
    }

    missing_device_response = client.get(
        f"/devices/{missing_device_id}",
        headers=AUTH_HEADERS,
    )
    assert missing_device_response.status_code == 404
    assert missing_device_response.json() == {
        "code": "DEVICE_NOT_FOUND",
        "message": "Device not found",
    }

    validation_response = client.post(
        "/users/",
        headers=AUTH_HEADERS,
        json={"beta_code": ""},
    )
    assert validation_response.status_code == 422
    validation_error = validation_response.json()
    assert validation_error["code"] == "VALIDATION_ERROR"
    assert validation_error["message"] == "Request validation failed"
    assert validation_error["errors"]


def test_upload_completed_requires_file_keys() -> None:
    auth_headers, _ = create_auth_headers()
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"

    start_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "device_code": device_code,
            "started_at": "2026-09-05T15:00:00Z",
        },
    )
    assert start_response.status_code == 201
    session_id = start_response.json()["session_id"]

    upload_response = client.patch(
        f"/sleep-sessions/{session_id}/upload",
        headers=auth_headers,
        json={"upload_status": "completed"},
    )
    assert upload_response.status_code == 400
    assert upload_response.json() == {
        "code": "UPLOAD_FILES_REQUIRED",
        "message": (
            "sensor_file_key and prediction_file_key are required "
            "when upload_status is completed"
        ),
    }


def test_raw_multipart_upload_flow_for_android_app_contract() -> None:
    auth_headers, user_id = create_auth_headers()
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"

    start_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "device_code": device_code,
            "started_at": "2026-09-05T15:00:00Z",
        },
    )
    assert start_response.status_code == 201
    session_id = start_response.json()["session_id"]

    raw_bytes = b"\0" * 150
    sha256 = "a" * 64
    file_name = f"potch_packet_raw_data_20260911_183104_123_{session_id}.bin"

    initiate_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads",
        headers={
            **auth_headers,
            "Idempotency-Key": f"{session_id}:raw:{sha256}",
        },
        json={
            "formatVersion": "potch-raw-v1",
            "fileName": file_name,
            "contentType": "application/octet-stream",
            "sizeBytes": len(raw_bytes),
            "recordSizeBytes": 150,
            "recordCount": 1,
            "sha256": sha256,
        },
    )
    assert initiate_response.status_code == 201
    initiated = initiate_response.json()
    upload_id = initiated["uploadId"]
    assert initiated["partSizeBytes"] == 8388608
    assert initiated["status"] == "UPLOADING"
    assert initiated["objectKey"] == (
        f"users/{user_id}/sleep-sessions/{session_id}/sensor.raw.v1.bin"
    )

    repeated_initiate_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads",
        headers=auth_headers,
        json={
            "formatVersion": "potch-raw-v1",
            "fileName": file_name,
            "contentType": "application/octet-stream",
            "sizeBytes": len(raw_bytes),
            "recordSizeBytes": 150,
            "recordCount": 1,
            "sha256": sha256,
        },
    )
    assert repeated_initiate_response.status_code == 200
    assert repeated_initiate_response.json()["uploadId"] == upload_id

    status_response = client.get(
        f"/v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}",
        headers=auth_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["uploadedParts"] == []

    checksum_crc32c = "AAAAAA=="
    presign_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}/parts/presign",
        headers=auth_headers,
        json={
            "partNumber": 1,
            "sizeBytes": len(raw_bytes),
            "checksumCrc32c": checksum_crc32c,
        },
    )
    assert presign_response.status_code == 200
    presigned = presign_response.json()
    assert presigned["partNumber"] == 1
    assert presigned["headers"] == {"x-amz-checksum-crc32c": checksum_crc32c}

    local_upload_path = urlparse(presigned["url"]).path
    put_response = client.put(
        local_upload_path,
        content=raw_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "x-amz-checksum-crc32c": checksum_crc32c,
        },
    )
    assert put_response.status_code == 200
    etag = put_response.headers["etag"]

    complete_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}/complete",
        headers=auth_headers,
        json={
            "parts": [
                {
                    "partNumber": 1,
                    "etag": etag,
                    "checksumCrc32c": checksum_crc32c,
                }
            ],
            "sizeBytes": len(raw_bytes),
            "sha256": sha256,
        },
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()
    assert completed["status"] == "COMPLETE"
    assert completed["sizeBytes"] == len(raw_bytes)

    detail_response = client.get(
        f"/sleep-sessions/{session_id}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["sensor_file_key"] == completed["objectKey"]
    assert detail["upload_status"] == "completed"


def test_raw_multipart_upload_requires_member_token() -> None:
    auth_headers, user_id = create_auth_headers()
    device_code = f"TEST_DEV_{uuid.uuid4().hex}"

    start_response = client.post(
        "/sleep-sessions/start",
        headers=auth_headers,
        json={
            "device_code": device_code,
            "started_at": "2026-09-05T15:00:00Z",
        },
    )
    assert start_response.status_code == 201
    session_id = start_response.json()["session_id"]
    sha256 = "c" * 64
    raw_upload_payload = {
        "formatVersion": "potch-raw-v1",
        "fileName": f"potch_packet_raw_data_20260911_183104_123_{session_id}.bin",
        "contentType": "application/octet-stream",
        "sizeBytes": 150,
        "recordSizeBytes": 150,
        "recordCount": 1,
        "sha256": sha256,
    }

    missing_token_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads",
        json=raw_upload_payload,
    )
    assert missing_token_response.status_code == 401
    assert missing_token_response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Authorization bearer token is required",
    }

    api_key_only_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads",
        headers=AUTH_HEADERS,
        json=raw_upload_payload,
    )
    assert api_key_only_response.status_code == 401
    assert api_key_only_response.json()["code"] == "AUTHENTICATION_REQUIRED"

    extra_user_field_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads",
        headers=auth_headers,
        json={
            **raw_upload_payload,
            "userId": str(uuid.uuid4()),
            "objectKey": "users/someone-else/sleep-sessions/wrong/sensor.raw.v1.bin",
        },
    )
    assert extra_user_field_response.status_code == 422
    assert extra_user_field_response.json()["code"] == "VALIDATION_ERROR"

    initiate_response = client.post(
        f"/v1/sleep-sessions/{session_id}/raw-uploads",
        headers=auth_headers,
        json=raw_upload_payload,
    )
    assert initiate_response.status_code == 201
    initiated = initiate_response.json()
    assert initiated["objectKey"] == (
        f"users/{user_id}/sleep-sessions/{session_id}/sensor.raw.v1.bin"
    )
