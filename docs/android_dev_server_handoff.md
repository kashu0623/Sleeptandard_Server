# Android 개발 서버 연결 정보

작성일: 2026-09-28  
대상: `Sleeptandard_Android`의 로그인/회원가입 및 Potch raw 업로드 구현

## 현재 상태

Elastic Beanstalk 개발 환경은 생성되어 있습니다.

```text
환경 이름: sleeptandard-api-dev
예정 Base URL: http://sleeptandard-api-dev.ap-northeast-2.elasticbeanstalk.com
```

단, 위 주소에는 아직 FastAPI와 개발 DB 설정이 배포되지 않았습니다. 현재는 AWS 샘플 앱 상태이므로 **앱 연결용으로 사용하지 마세요.** 서버 배포, DB migration, `/health` 확인이 끝난 뒤 서버 담당자가 연결 가능 여부와 최종 URL을 다시 공지합니다.

## Android 설정값

FastAPI가 배포 완료되면 Android 프로젝트의 로컬 개발자 설정 파일에 다음 값을 넣습니다.

```properties
# local.properties
SLEEP_SERVER_BASE_URL=http://sleeptandard-api-dev.ap-northeast-2.elasticbeanstalk.com
```

현재 `app/build.gradle.kts`가 이 값을 `BuildConfig.SLEEP_SERVER_BASE_URL`로 전달하고, raw 업로더는 끝의 `/`를 자동으로 제거합니다.

이 URL은 현재 HTTP입니다. Android 9 이상에서는 HTTP 요청을 기본적으로 막을 수 있으므로, HTTPS가 준비되기 전에는 **debug 빌드에서만** cleartext HTTP를 허용하는 설정이 필요할 수 있습니다. 운영/release 빌드에는 적용하지 않고, HTTPS URL이 준비되면 해당 임시 설정을 제거합니다.

앱에 설정하거나 포함하면 안 되는 값:

- `X-API-Key` 또는 기존 Supabase anon key
- AWS Access Key, Secret Key, S3 버킷 쓰기 권한
- S3 object key를 직접 만드는 규칙

Raw 파일은 앱이 S3 권한을 갖고 직접 인증하는 구조가 아니라, FastAPI가 발급한 짧은 수명의 presigned URL로 업로드합니다.

## 인증 방식

### 1. 회원가입

`POST /auth/signup`

```json
{
  "email": "tester@example.com",
  "password": "at-least-8-characters",
  "nickname": "chan",
  "gender": "male",
  "birthdate": "2000-01-01"
}
```

- `gender`, `birthdate`는 선택값입니다.
- `gender`는 `male`, `female`, `other`, `prefer_not_to_say` 중 하나입니다.
- 비밀번호는 8자 이상입니다.
- 성공하면 `201 Created`와 함께 로그인 토큰을 반환합니다.

### 2. 로그인

`POST /auth/login`

```json
{
  "email": "tester@example.com",
  "password": "at-least-8-characters"
}
```

### 3. 응답 및 저장

회원가입과 로그인 모두 아래 형식으로 응답합니다.

```json
{
  "access_token": "<FastAPI access token>",
  "token_type": "bearer",
  "expires_in": 604800,
  "user": {
    "user_id": "<UUID>",
    "email": "tester@example.com",
    "nickname": "chan",
    "gender": "male",
    "birthdate": "2000-01-01"
  }
}
```

- `access_token` 만 앱의 암호화된 로그인 세션 저장소에 저장합니다.
- `user.user_id`는 화면 상태와 수면기록 조회 경로에 사용합니다.
- 토큰 유효기간은 현재 7일(`604800`초)입니다. 만료 또는 `401` 응답 시 로그인 화면으로 보냅니다.
- Supabase 세션/토큰을 새 서버에 재사용하지 않습니다.

### 4. 인증 헤더

로그인 후 사용자 API에는 모두 아래 헤더를 넣습니다.

```http
Authorization: Bearer <access_token>
```

`SleepServerAuthProvider.bearerToken()`은 위 암호화된 저장소에서 이 토큰을 읽어 반환하도록 구현합니다. Raw 업로드 `WorkManager`도 같은 토큰을 사용합니다.

현재 로그인 사용자 확인 API:

```http
GET /auth/me
Authorization: Bearer <access_token>
```

## 앱이 사용할 API

모든 경로는 `SLEEP_SERVER_BASE_URL` 뒤에 붙입니다. 별도 표기가 없는 API는 `Authorization: Bearer <access_token>`이 필요합니다.

| 목적 | 메서드 | 경로 | 핵심 결과 |
| --- | --- | --- | --- |
| 회원가입 | `POST` | `/auth/signup` | 사용자 정보와 access token 반환 |
| 로그인 | `POST` | `/auth/login` | 사용자 정보와 access token 반환 |
| 내 정보 확인 | `GET` | `/auth/me` | 현재 토큰의 사용자 정보 반환 |
| 수면 측정 시작 | `POST` | `/sleep-sessions/start` | `session_id` 반환 |
| 수면 측정 종료 | `PATCH` | `/sleep-sessions/{session_id}/finish` | 세션을 `completed`로 변경 |
| 수면 측정 중단 | `PATCH` | `/sleep-sessions/{session_id}/abort` | 세션을 `aborted`로 변경 |
| 세션 상세 조회 | `GET` | `/sleep-sessions/{session_id}` | 요약, 알람, 상태 포함 |
| 내 수면기록 목록 | `GET` | `/users/{user_id}/sleep-sessions?limit=20&offset=0` | 해당 사용자 본인만 조회 가능 |
| 알람 이벤트 저장 | `POST` | `/sleep-sessions/{session_id}/alarm-events` | 알람 1건 저장 |
| 수면 요약 저장 | `POST` | `/sleep-sessions/{session_id}/summary` | 종료된 세션의 요약 저장/갱신 |
| raw 업로드 시작 | `POST` | `/v1/sleep-sessions/{session_id}/raw-uploads` | `uploadId`, `partSizeBytes`, presigned-upload 준비 |
| raw 업로드 재개 확인 | `GET` | `/v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}` | 이미 올라간 part 목록 반환 |
| part URL 발급 | `POST` | `/v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}/parts/presign` | S3 `PUT` URL과 필수 헤더 반환 |
| raw 업로드 완료 | `POST` | `/v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}/complete` | multipart 업로드 완료 처리 |
| raw 업로드 취소 | `DELETE` | `/v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}` | 업로드 중단 |

수면기록 목록의 `{user_id}`는 로그인/회원가입 응답 또는 `/auth/me`의 `user_id`를 사용합니다. 다른 사용자의 `user_id`를 넣으면 서버가 거부합니다.

## 수면 세션 시작 규칙

수면을 측정하기 시작할 때 앱은 먼저 아래 API를 호출해야 합니다.

`POST /sleep-sessions/start`

```json
{
  "device_code": "DEV001",
  "hardware_revision": "HW_REV_A",
  "firmware_version": "0.8.1",
  "model_version": "sleep_4class_v1.0",
  "app_version": "0.9.0",
  "os_type": "android",
  "os_version": "16",
  "ppg_sampling_rate_hz": 100,
  "acc_sampling_rate_hz": 100,
  "temp_sampling_rate_hz": 1,
  "started_at": "2026-09-28T08:00:00Z"
}
```

응답의 `session_id`를 앱 측정 상태와 raw 파일 이름에 저장합니다.

```json
{
  "session_id": "<UUID>",
  "session_status": "recording",
  "upload_status": "pending"
}
```

`user_id`, `beta_code`, S3 bucket, object key는 요청에 넣지 않습니다. 사용자는 Bearer 토큰으로 서버가 결정하고, S3 저장 위치는 raw 업로드 시작 API가 결정합니다.

## Raw multipart 업로드 규칙

상세 계약은 Android 저장소의 `docs/potch-raw-upload-api.md`를 기준으로 합니다. 서버와 맞춰야 할 핵심 값은 아래와 같습니다.

1. 수면 시작 응답의 `session_id`가 포함된 raw 파일을 닫습니다.
2. `POST /v1/sleep-sessions/{session_id}/raw-uploads`를 호출합니다.
3. 서버 응답의 `partSizeBytes` 단위로 파일을 나눕니다. 현재 값은 `8388608`(8 MiB)입니다.
4. 각 part마다 CRC32C를 계산하고 presign API를 호출합니다.
5. 응답의 URL로 S3에 `PUT`합니다. 응답 `headers`의 `x-amz-checksum-crc32c`를 그대로 넣고, S3 응답 `ETag`를 저장합니다.
6. 모든 part의 `partNumber`, `ETag`, `checksumCrc32c`를 complete API로 보냅니다.

Raw 업로드 시작 요청의 고정값:

```json
{
  "formatVersion": "potch-raw-v1",
  "contentType": "application/octet-stream",
  "recordSizeBytes": 150
}
```

추가 검증 규칙:

- `fileName`에는 현재 `session_id` 문자열이 포함되어야 합니다.
- `sizeBytes`는 150의 배수여야 합니다.
- `recordCount`는 `sizeBytes / 150`과 일치해야 합니다.
- 마지막 part를 제외한 각 part는 5 MiB 이상이어야 합니다.
- S3 URL이 만료되면 새 presign URL을 받아 다시 전송합니다.
- 앱은 서버가 돌려준 `objectKey`를 표시/기록할 수는 있지만, 생성하거나 변경하지 않습니다.

Android native 앱의 S3 업로드에는 웹 브라우저 CORS 설정이 필요하지 않습니다.

## 오류 응답

서버 오류는 아래와 같이 일관된 JSON으로 반환됩니다.

```json
{
  "code": "INVALID_LOGIN_CREDENTIALS",
  "message": "Invalid email or password"
}
```

입력 검증 오류(`422`)에는 `errors` 배열이 추가됩니다. 앱은 HTTP 상태 코드와 `code`를 기준으로 처리합니다.

주요 처리 기준:

| 상태 | 예시 code | 앱 동작 |
| --- | --- | --- |
| `401` | `INVALID_LOGIN_CREDENTIALS` | 로그인 입력 오류 안내 |
| `401` | `INVALID_ACCESS_TOKEN` 등 | 세션 삭제 후 재로그인 |
| `403` | `SLEEP_SESSION_FORBIDDEN` | 다른 사용자 세션 접근 금지 |
| `409` | `EMAIL_ALREADY_EXISTS` | 회원가입 이메일 중복 안내 |
| `409` | `UPLOAD_PART_MISSING` | 업로드 상태 조회 후 재시도 |
| `422` | `VALIDATION_ERROR` | 앱 요청 payload 확인 |

## 서버 담당자 공지 후 확인할 항목

서버 배포가 끝나면 아래만 다시 확인하면 됩니다.

1. `GET /health`가 `{ "status": "ok" }`를 반환하는지
2. `GET /health/db`가 DB 연결 성공을 반환하는지
3. Swagger 문서 `GET /docs`가 열리는지
4. Base URL이 HTTPS로 바뀌었는지, 또는 debug HTTP 예외가 필요한지
5. 회원가입 → 로그인 → 수면 시작 → raw 업로드 → 수면 종료의 실제 단말 통합 테스트가 통과하는지
