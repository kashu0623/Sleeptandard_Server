# 서버 및 CloudWatch 로그 운영 가이드

이 문서는 Sleeptandard 개발 서버에서 문제를 추적할 때 사용하는 로그 기준을 정리합니다.

## 1. 기록되는 로그

FastAPI는 한 줄에 하나의 JSON 로그를 표준 출력으로 기록합니다.

```json
{
  "timestamp": "2026-10-05T03:00:00+00:00",
  "level": "INFO",
  "service": "sleeptandard-api",
  "environment": "dev",
  "logger": "sleeptandard.raw_upload",
  "event": "raw_upload.completed",
  "request_id": "4cb76825-1c3e-47bb-a136-c95ed2dc1114",
  "sleep_session_id": "...",
  "upload_id": "...",
  "upload_status": "COMPLETE",
  "attempt_count": 2,
  "size_bytes": 391200
}
```

주요 이벤트는 다음과 같습니다.

```text
auth.signup_succeeded
auth.login_succeeded
sleep_session.started
sleep_session.completed
sleep_session.aborted
raw_upload.initiated
raw_upload.reused
raw_upload.attempted
raw_upload.failed
raw_upload.completed
raw_upload.aborted
request.rejected
request.validation_failed
request.unhandled_error
request.completed
```

성공한 `/health`, `/health/db` 요청은 로그 양을 줄이기 위해 기본적으로 기록하지 않습니다. 실패한 경우에는 기록됩니다.

## 2. 개인정보 및 비밀값 기준

다음 값은 애플리케이션 로그에 기록하지 않습니다.

```text
비밀번호와 password hash
Authorization bearer token
X-API-Key
presigned S3 URL
요청 및 응답 본문
이메일과 닉네임
raw 센서 데이터 내용
```

사용자, 수면 세션, 업로드 문제를 연결할 때는 UUID와 오류 코드만 사용합니다.

## 3. Request ID 사용

모든 API 응답에는 아래 헤더가 포함됩니다.

```text
X-Request-ID: 4cb76825-1c3e-47bb-a136-c95ed2dc1114
```

앱이 `X-Request-ID`를 보내면 안전한 형식일 때 동일한 값을 사용합니다. 보내지 않으면 서버가 UUID를 생성합니다.

앱 개발자가 오류를 공유할 때 아래 세 값을 함께 전달하면 서버 로그를 빠르게 찾을 수 있습니다.

```text
발생 시각
X-Request-ID
sleep_session_id 또는 upload_id
```

## 4. CloudWatch 저장 위치

Elastic Beanstalk 환경 이름이 `sleeptandard-api-dev`인 경우 애플리케이션 JSON 로그는 다음 로그 그룹에서 확인합니다.

```text
/aws/elasticbeanstalk/sleeptandard-api-dev/var/log/web.stdout.log
```

함께 전송되는 주요 로그는 다음과 같습니다.

```text
/aws/elasticbeanstalk/sleeptandard-api-dev/var/log/nginx/access.log
/aws/elasticbeanstalk/sleeptandard-api-dev/var/log/nginx/error.log
/aws/elasticbeanstalk/sleeptandard-api-dev/var/log/eb-engine.log
```

개발 환경 로그와 상태 로그의 보관 기간은 30일이며, 환경을 삭제해도 보관 기간 동안 로그 그룹을 유지합니다.

## 5. CloudWatch Logs Insights 검색 예시

최근 실패한 raw 업로드:

```text
fields @timestamp, request_id, sleep_session_id, upload_id, error_code, retryable
| filter event = "raw_upload.failed"
| sort @timestamp desc
| limit 50
```

특정 업로드의 전체 흐름:

```text
fields @timestamp, level, event, request_id, upload_status, attempt_count, error_code
| filter upload_id = "UPLOAD_UUID"
| sort @timestamp asc
```

5xx 서버 오류:

```text
fields @timestamp, event, request_id, method, route, status_code, exception
| filter status_code >= 500
| sort @timestamp desc
| limit 50
```

느린 API 요청:

```text
fields @timestamp, request_id, method, route, status_code, duration_ms
| filter event = "request.completed" and duration_ms >= 1000
| sort duration_ms desc
| limit 50
```

## 6. 환경변수

```text
APP_ENV=dev
LOG_LEVEL=INFO
LOG_SERVICE_NAME=sleeptandard-api
LOG_HEALTH_REQUESTS=false
```

문제 조사 중에도 `DEBUG` 로그를 장기간 유지하지 않습니다. 요청 본문이나 인증값을 출력하는 임시 로그는 추가하지 않습니다.
