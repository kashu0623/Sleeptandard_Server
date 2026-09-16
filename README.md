# Wearable Sleep API

웨어러블 수면 베타 v1용 FastAPI 백엔드입니다.

## 이번에 만드는 것

1. 프로젝트 폴더와 가상환경
   - Python 패키지를 이 프로젝트 안에만 설치하기 위해 필요합니다.
2. FastAPI 실행 확인
   - 서버가 켜지고 `/health`가 응답하는지 먼저 확인합니다.
3. Docker Compose PostgreSQL
   - 로컬 컴퓨터에 실제 PostgreSQL DB를 하나 띄웁니다.
4. SQLAlchemy 연결
   - FastAPI 코드가 PostgreSQL에 접속할 수 있게 합니다.
5. Alembic 설정
   - DB 테이블 변경 이력을 migration 파일로 관리합니다.
6. 테이블 모델 작성
   - `users`, `devices`, `sleep_sessions`, `sleep_summaries`, `alarm_events`를 코드로 정의합니다.
7. 첫 migration 적용
   - 모델 정의를 실제 PostgreSQL 테이블로 생성합니다.
8. Health check와 DB 연결 테스트
   - 앱 서버와 DB 연결이 모두 살아 있는지 확인합니다.

## 로컬 실행 순서

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

로컬 S3 URL 테스트용 설정은 `.env`에 들어 있습니다.

```text
API_KEY=local-dev-api-key
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=local-test-access-key
AWS_SECRET_ACCESS_KEY=local-test-secret-key
S3_BUCKET_NAME=wearable-sleep-local
S3_UPLOAD_URL_EXPIRES_SEC=900
```

`API_KEY`는 로컬 개발용 서버 비밀번호처럼 쓰입니다.
`AWS_...`와 `S3_...` 값들은 로컬에서 URL 생성 흐름을 확인하기 위한 더미 값입니다.
실제 S3에 업로드하려면 나중에 AWS에서 만든 실제 버킷과 권한 값으로 바꿔야 합니다.

서버 확인:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
```

인증이 필요한 API는 요청마다 아래 헤더를 붙입니다.

```text
X-API-Key: local-dev-api-key
```

`/health`, `/health/db`는 서버 상태 확인용이어서 API Key 없이 열어둡니다.

API 문서 확인:

```text
http://127.0.0.1:8000/docs
```

FastAPI는 서버가 켜지면 API 문서를 자동으로 만들어줍니다.

- `health`: 서버와 DB 연결 확인
- `users`: 베타테스터 등록, 조회, 사용자별 수면 기록 목록
- `devices`: 웨어러블 기기 등록과 조회
- `sleep_sessions`: 수면 시작, 종료, 중단, 알람, 요약, S3 업로드 URL, 업로드 상태, 상세 조회

개발 중에는 이 문서 화면에서 각 API의 요청값과 응답값을 확인할 수 있습니다.
문서 화면 오른쪽 위 `Authorize` 버튼을 누르고 `local-dev-api-key`를 입력하면,
보호된 API도 문서 화면에서 직접 호출할 수 있습니다.

베타테스터 등록 API 확인:

```bash
curl -X POST http://127.0.0.1:8000/users/ \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "beta_code": "BETA001"
  }'
```

베타테스터 조회 API 확인:

```bash
curl http://127.0.0.1:8000/users/{user_id} \
  -H "X-API-Key: local-dev-api-key"
```

이 API는 앱 최초 등록 또는 베타 코드 입력 화면에서 사용합니다.

- `beta_code`로 `users` row를 생성합니다.
- 같은 `beta_code`로 다시 호출하면 기존 사용자를 반환합니다.
- 수면 측정 시작 API는 여기서 받은 `user_id`를 나중에 앱 내부에 저장해 활용할 수 있습니다.

기기 등록 API 확인:

```bash
curl -X POST http://127.0.0.1:8000/devices/ \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "device_code": "DEV001",
    "hardware_revision": "HW_REV_A",
    "firmware_version": "0.8.1"
  }'
```

기기 조회 API 확인:

```bash
curl http://127.0.0.1:8000/devices/{device_id} \
  -H "X-API-Key: local-dev-api-key"
```

이 API는 앱에서 BLE 기기를 등록하거나 이미 등록된 기기 정보를 확인할 때 사용합니다.

- `device_code`로 `devices` row를 생성합니다.
- 같은 `device_code`로 다시 호출하면 기존 기기를 반환합니다.
- `hardware_revision`이나 `firmware_version`이 들어오면 최신 값으로 갱신합니다.

수면 측정 시작 API 확인:

```bash
curl -X POST http://127.0.0.1:8000/sleep-sessions/start \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "beta_code": "BETA001",
    "device_code": "DEV001",
    "hardware_revision": "HW_REV_A",
    "firmware_version": "0.8.1",
    "model_version": "sleep_4class_v1.0",
    "app_version": "0.9.0",
    "os_type": "ios",
    "os_version": "18.0",
    "ppg_sampling_rate_hz": 100,
    "acc_sampling_rate_hz": 100,
    "temp_sampling_rate_hz": 1
  }'
```

이 API는 앱에서 수면 측정 시작 버튼을 눌렀을 때 호출합니다.

- `users`에서 `beta_code`를 찾고, 없으면 새 베타테스터로 생성합니다.
- `devices`에서 `device_code`를 찾고, 없으면 새 기기로 생성합니다.
- `sleep_sessions`에 새 수면 측정 row를 생성합니다.
- 앱이 이후 데이터 저장에 사용할 `session_id`를 반환합니다.

수면 측정 종료 API 확인:

```bash
curl -X PATCH http://127.0.0.1:8000/sleep-sessions/{session_id}/finish \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{}'
```

`{session_id}` 자리에는 수면 측정 시작 API에서 받은 값을 넣습니다.

이 API는 앱에서 수면 측정 종료 버튼을 눌렀을 때 호출합니다.

- 기존 `sleep_sessions` row를 찾습니다.
- `ended_at`이 비어 있으면 현재 시간을 저장합니다.
- `started_at`과 `ended_at` 차이로 `duration_sec`을 계산합니다.
- `session_status`를 `completed`로 바꿉니다.
- `upload_status`는 파일 업로드 상태이므로 여기서는 그대로 둡니다.

알람 이벤트 저장 API 확인:

```bash
curl -X POST http://127.0.0.1:8000/sleep-sessions/{session_id}/alarm-events \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "scheduled_at": "2026-09-05T22:55:00Z",
    "triggered_at": "2026-09-05T22:50:00Z",
    "alarm_type": "smart_alarm",
    "sleep_stage": "light",
    "confidence": 0.87,
    "reason": "Light sleep detected inside alarm window"
  }'
```

이 API는 스마트 알람이 실제로 울린 순간 호출합니다.

- 기존 `sleep_sessions` row를 찾습니다.
- `alarm_events`에 새 알람 이벤트 row를 생성합니다.
- `triggered_at`이 없으면 현재 시간을 저장합니다.
- 앱이나 서버가 나중에 어떤 수면 단계에서 왜 알람을 울렸는지 확인할 수 있게 합니다.

수면 요약 저장 API 확인:

```bash
curl -X POST http://127.0.0.1:8000/sleep-sessions/{session_id}/summary \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "total_sleep_sec": 25200,
    "awake_sec": 1800,
    "rem_sec": 5400,
    "light_sec": 12600,
    "deep_sec": 7200,
    "sleep_score": 86,
    "summary_json": {
      "note": "Good sleep continuity",
      "stage_model": "sleep_4class_v1.0"
    }
  }'
```

이 API는 수면 측정이 종료된 뒤 호출합니다.

- 기존 `sleep_sessions` row가 `completed` 상태인지 확인합니다.
- `sleep_summaries`에 세션당 하나의 요약 row를 저장합니다.
- 같은 세션으로 다시 호출하면 기존 요약 row를 갱신합니다.
- 단계별 수면 시간, 수면 점수, 추가 분석 JSON을 보관합니다.

S3 업로드 URL 발급 API 확인:

```bash
curl -X POST http://127.0.0.1:8000/sleep-sessions/{session_id}/upload-urls \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_content_type": "application/octet-stream",
    "prediction_content_type": "application/json"
  }'
```

이 API는 앱이 센서 원본 파일과 AI 예측 파일을 S3에 직접 업로드하기 전에 호출합니다.

- 서버가 `sensor_file_key`, `prediction_file_key`를 정해 DB에 저장합니다.
- `upload_status`를 `uploading`으로 바꿉니다.
- 앱이 S3에 직접 업로드할 수 있는 임시 URL을 반환합니다.
- 로컬 더미 설정에서는 URL 모양만 확인할 수 있고, 실제 업로드는 진짜 AWS 설정이 필요합니다.

파일 업로드 상태 저장 API 확인:

```bash
curl -X PATCH http://127.0.0.1:8000/sleep-sessions/{session_id}/upload \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_file_key": "sleep-sessions/{session_id}/sensor.parquet",
    "prediction_file_key": "sleep-sessions/{session_id}/prediction.json",
    "upload_status": "completed"
  }'
```

이 API는 센서 원본 파일과 AI 예측 파일을 S3 같은 저장소에 올린 뒤 호출합니다.

- `sensor_file_key`에 센서 파일 위치를 저장합니다.
- `prediction_file_key`에 AI 예측 파일 위치를 저장합니다.
- `upload_status`를 `pending`, `uploading`, `completed`, `failed` 중 하나로 저장합니다.
- `completed`로 바꿀 때는 두 파일 키가 모두 있어야 합니다.

수면 세션 조회 API 확인:

```bash
curl http://127.0.0.1:8000/sleep-sessions/{session_id} \
  -H "X-API-Key: local-dev-api-key"
```

이 API는 수면 기록 상세 화면을 보여줄 때 호출합니다.

- `sleep_sessions`의 기본 정보를 가져옵니다.
- 연결된 `sleep_summaries` 요약 정보를 같이 가져옵니다.
- 연결된 `alarm_events` 목록을 같이 가져옵니다.
- 센서 파일 키, 예측 파일 키, 측정 상태, 업로드 상태를 한 번에 확인할 수 있습니다.

사용자별 수면 기록 목록 API 확인:

```bash
curl "http://127.0.0.1:8000/users/{user_id}/sleep-sessions?limit=20&offset=0" \
  -H "X-API-Key: local-dev-api-key"
```

`{user_id}` 자리에는 수면 측정 시작 API에서 받은 값을 넣습니다.

이 API는 앱의 지난 수면 기록 목록 화면에서 호출합니다.

- 특정 사용자의 `sleep_sessions` 목록을 최신순으로 가져옵니다.
- 목록에 필요한 시작 시간, 종료 시간, 상태, 수면 점수를 내려줍니다.
- `limit`과 `offset`으로 기록을 나눠 가져올 수 있습니다.
- 상세 화면이 필요하면 각 항목의 `session_id`로 수면 세션 조회 API를 호출합니다.

수면 측정 중단 API 확인:

```bash
curl -X PATCH http://127.0.0.1:8000/sleep-sessions/{session_id}/abort \
  -H "X-API-Key: local-dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{}'
```

`{session_id}` 자리에는 수면 측정 시작 API에서 받은 값을 넣습니다.

이 API는 앱이 중간에 꺼졌거나 사용자가 측정을 취소했을 때 호출합니다.

- 기존 `sleep_sessions` row를 찾습니다.
- `ended_at`이 비어 있으면 현재 시간을 저장합니다.
- `started_at`과 `ended_at` 차이로 `duration_sec`을 계산합니다.
- `session_status`를 `aborted`로 바꿉니다.
- 이미 `completed`인 세션은 중단 처리하지 않습니다.

DB 테이블 확인:

```bash
python scripts/check_db.py
```

## SQLAlchemy + Alembic 작업 방식

SQLAlchemy는 Python 코드에서 DB 테이블을 다루기 위한 도구입니다.

- `app/db/base.py`는 모든 모델이 공유하는 기본 클래스입니다.
- `app/db/session.py`는 FastAPI가 PostgreSQL에 접속할 때 쓰는 연결 통로입니다.
- `app/models.py`는 실제 테이블 구조를 Python 클래스로 정의합니다.

Alembic은 테이블 변경 이력을 관리하는 도구입니다.

- `alembic.ini`는 Alembic의 기본 설정 파일입니다.
- `migrations/env.py`는 SQLAlchemy 모델 정보를 Alembic에 연결합니다.
- `migrations/versions/`에는 실제 migration 파일들이 쌓입니다.

테이블을 바꾸는 기본 순서:

```bash
# 1. app/models.py 수정

# 2. 모델과 DB 차이를 migration 파일로 생성
alembic revision --autogenerate -m "describe change"

# 3. 생성된 migration 파일 검토

# 4. PostgreSQL에 적용
alembic upgrade head

# 5. 모델과 DB가 같은지 확인
alembic check
```

현재 DB migration 상태 확인:

```bash
alembic current
alembic heads
```

## API 테스트 자동화

테스트 자동화는 사람이 매번 `curl`로 확인하지 않아도 API가 제대로 동작하는지 검사하는 장치입니다.

테스트 실행 전 PostgreSQL이 켜져 있어야 합니다.

```bash
docker compose up -d
source .venv/bin/activate
pytest
```

테스트가 확인하는 것:

- 서버 health check가 정상인지 확인합니다.
- DB health check가 정상인지 확인합니다.
- 베타테스터와 기기 등록/조회가 정상인지 확인합니다.
- 같은 `beta_code`, `device_code`를 다시 등록해도 기존 row가 재사용되는지 확인합니다.
- 수면 시작, 알람 이벤트 저장, 정상 종료, 요약 저장, 업로드 상태 저장, 상세 조회, 목록 조회 흐름을 확인합니다.
- 수면 중단 후 요약 저장이 막히는지 확인합니다.

테스트 데이터는 `TEST_`로 시작하는 `beta_code`, `device_code`만 사용하고 테스트 전후로 정리합니다.

## 에러 응답 형식

API 에러 응답은 앱에서 처리하기 쉽도록 같은 모양을 사용합니다.

```json
{
  "code": "SLEEP_SESSION_NOT_FOUND",
  "message": "Sleep session not found"
}
```

입력값 검증에 실패하면 `errors` 배열이 함께 내려옵니다.

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "errors": []
}
```

주요 에러 코드:

- `USER_NOT_FOUND`: 사용자를 찾을 수 없습니다.
- `DEVICE_NOT_FOUND`: 기기를 찾을 수 없습니다.
- `SLEEP_SESSION_NOT_FOUND`: 수면 세션을 찾을 수 없습니다.
- `SLEEP_SESSION_ABORTED`: 중단된 수면 세션에는 해당 작업을 할 수 없습니다.
- `SLEEP_SESSION_ALREADY_COMPLETED`: 이미 완료된 수면 세션은 중단 처리할 수 없습니다.
- `INVALID_SESSION_TIME_RANGE`: 종료 시간이 시작 시간보다 빠릅니다.
- `SLEEP_SUMMARY_SESSION_NOT_COMPLETED`: 완료되지 않은 세션에는 수면 요약을 저장할 수 없습니다.
- `UPLOAD_FILES_REQUIRED`: 업로드 완료 상태에는 센서 파일 키와 예측 파일 키가 모두 필요합니다.
- `VALIDATION_ERROR`: 요청 형식이나 입력값이 올바르지 않습니다.

## 확정된 DB Schema v1

### users

베타테스터 한 명당 한 번 생성합니다.

- `id`
- `beta_code`
- `created_at`
- `updated_at`

### devices

웨어러블 기기 한 대당 한 번 생성합니다.

- `id`
- `device_code`
- `hardware_revision`
- `firmware_version`
- `created_at`
- `updated_at`

### sleep_sessions

사용자가 수면 측정을 시작할 때마다 새로 생성합니다.

- `id`
- `user_id`
- `device_id`
- `started_at`
- `ended_at`
- `duration_sec`
- `model_version`
- `app_version`
- `firmware_version`
- `os_type`
- `os_version`
- `ppg_sampling_rate_hz`
- `acc_sampling_rate_hz`
- `temp_sampling_rate_hz`
- `sensor_file_key`
- `prediction_file_key`
- `session_status`
- `upload_status`
- `created_at`
- `updated_at`

`session_status`는 수면 측정 자체의 상태입니다.

- `recording`
- `completed`
- `aborted`

`upload_status`는 S3 업로드 상태입니다.

- `pending`
- `uploading`
- `completed`
- `failed`

### sleep_summaries

수면 측정이 끝난 뒤 세션당 한 번 생성합니다.

- `id`
- `sleep_session_id`
- `total_sleep_sec`
- `awake_sec`
- `rem_sec`
- `light_sec`
- `deep_sec`
- `sleep_score`
- `summary_json`
- `created_at`
- `updated_at`

### alarm_events

스마트 알람이 울릴 때마다 생성합니다.

- `id`
- `sleep_session_id`
- `scheduled_at`
- `triggered_at`
- `alarm_type`
- `sleep_stage`
- `confidence`
- `reason`
- `created_at`
- `updated_at`
