# Sleeptandard Android server_test Raw Upload Notes

이 문서는 Android 앱의 `Sleeptandard_Android/server_test` 브랜치와 현재 로컬 FastAPI 백엔드를 비교하기 위한 개인 메모입니다.
README에 바로 반영하지 않고, 나중에 필요한 내용만 골라 옮기기 위한 용도입니다.

## 확인한 앱 저장소

```text
경로: /Users/chan/Documents/Sleeptandard_Android
브랜치: server_test
최근 커밋: Feat: raw 데이터 전송 구조 설계완료
```

앱 쪽 핵심 파일:

- `/Users/chan/Documents/Sleeptandard_Android/docs/potch-raw-upload-api.md`
- `/Users/chan/Documents/Sleeptandard_Android/app/src/main/java/com/leejang/sleeptandard/backend/RawDataUploadManager.kt`
- `/Users/chan/Documents/Sleeptandard_Android/app/src/main/java/com/leejang/sleeptandard/backend/RawDataUploadWorker.kt`
- `/Users/chan/Documents/Sleeptandard_Android/app/src/main/java/com/leejang/sleeptandard/backend/SleepServerAuthProvider.kt`
- `/Users/chan/Documents/Sleeptandard_Android/app/src/main/java/com/leejang/sleeptandard/backend/PotchRawFileContract.kt`

## 앱이 기대하는 흐름

```text
Potch raw .bin 파일 생성
↓
닫힌 파일만 업로드 예약
↓
FastAPI에 multipart 업로드 시작 요청
↓
FastAPI가 S3 업로드 ID와 object key 저장
↓
앱이 파트별 presigned URL 요청
↓
앱이 각 파트를 S3로 직접 PUT
↓
앱이 FastAPI에 complete 요청
↓
FastAPI가 sleep_sessions.sensor_file_key와 upload_status 갱신
```

## 앱이 기대하는 API

```text
POST   /v1/sleep-sessions/{session_id}/raw-uploads
GET    /v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}
POST   /v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}/parts/presign
POST   /v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}/complete
DELETE /v1/sleep-sessions/{session_id}/raw-uploads/{upload_id}
```

## 이번에 FastAPI 서버에 추가한 것

새 DB 테이블:

```text
sleep_session_uploads
```

역할:

- 앱에 노출하는 `uploadId` 저장
- 실제 S3 multipart upload id 저장
- 파일명, 크기, record 수, sha256 저장
- 업로드 상태 저장: `UPLOADING`, `COMPLETE`, `ABORTED`, `FAILED`
- 같은 파일을 다시 요청하면 기존 업로드를 반환할 수 있게 함

새 migration:

```text
migrations/versions/202609140001_create_sleep_session_uploads.py
```

새 라우터:

```text
app/routers/raw_uploads.py
```

S3 helper 확장:

```text
app/services/s3.py
```

## 로컬 테스트 모드

현재 `.env`에는 로컬 테스트용으로 아래 설정을 추가했습니다.

```text
AWS_S3_ENDPOINT_URL=
S3_MULTIPART_BACKEND=local
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

의미:

- `S3_MULTIPART_BACKEND=local`이면 실제 AWS S3에 올리지 않습니다.
- FastAPI가 S3 역할을 흉내 내는 임시 PUT URL을 발급합니다.
- 앱 연결 전, API 흐름 자체를 로컬에서 먼저 검증하기 위한 모드입니다.

실제 배포 시에는:

```text
S3_MULTIPART_BACKEND=aws
```

로 바꾸고, AWS S3 버킷과 IAM 권한을 연결해야 합니다.

## 인증 차이

앱 문서가 원래 기대한 인증:

```text
Authorization: Bearer <server-issued-access-token>
```

현재 로컬 FastAPI 인증:

```text
X-API-Key: local-dev-api-key
```

이번 서버 수정에서는 앱 테스트를 쉽게 하기 위해 둘 다 받을 수 있게 했습니다.

```text
X-API-Key: local-dev-api-key
Authorization: Bearer local-dev-api-key
```

나중에 실제 배포 단계에서는 임시 API Key 대신 로그인 기반 토큰 방식으로 바꾸는 것이 좋습니다.

## 앱 local.properties에 필요할 값

앱 저장소에는 아직 `local.properties`가 없었습니다.
로컬 폰/에뮬레이터에서 테스트하려면 앱 프로젝트에 아래 값을 넣어야 합니다.

```text
SLEEP_SERVER_BASE_URL=http://맥북_IP주소:8000
```

실제 Android 기기에서는 `127.0.0.1`을 쓰면 안 됩니다.
`127.0.0.1`은 폰 자기 자신을 뜻하기 때문입니다.

## 현재 검증 결과

서버 migration 적용:

```text
alembic upgrade head
```

정상 적용됨.

DB와 모델 차이 확인:

```text
alembic check
No new upgrade operations detected.
```

전체 테스트:

```text
8 passed, 3 warnings
```

추가된 테스트는 다음 흐름을 확인합니다.

```text
수면 세션 생성
↓
raw upload 시작
↓
같은 파일 재요청 시 기존 uploadId 반환
↓
part presigned URL 발급
↓
로컬 PUT URL로 1개 part 업로드
↓
complete 요청
↓
sleep_sessions.sensor_file_key 저장
↓
sleep_sessions.upload_status = completed
```

## 아직 남은 앱 연결 작업

1. 앱의 `SleepServerAuthProvider.kt`가 실제로 토큰을 반환하도록 수정해야 합니다.
   - 로컬 테스트 단계에서는 `local-dev-api-key`를 Bearer token처럼 반환해도 됩니다.

2. 앱의 `local.properties`에 `SLEEP_SERVER_BASE_URL`을 설정해야 합니다.

3. 앱이 FastAPI의 `POST /sleep-sessions/start`를 먼저 호출해서 `session_id`를 받아야 합니다.
   - 현재 raw 파일명은 마지막 UUID를 `sleep_session_id`로 사용합니다.
   - 앱이 이 UUID와 서버의 sleep session id를 같은 값으로 맞춰야 업로드가 자연스럽습니다.

4. 실제 AWS 배포 전에는 S3 multipart 모드를 `aws`로 바꾸고 실제 업로드를 검증해야 합니다.
