# AWS Elastic Beanstalk 개발 서버 배포 계획

이 문서는 Sleeptandard FastAPI 백엔드를 앱 테스트용 AWS 개발 서버로 배포하기 위한 개인용 체크리스트입니다.

목표는 운영 서버가 아니라 먼저 아래 흐름을 휴대폰 앱에서 테스트할 수 있는 dev API URL을 만드는 것입니다.

```text
회원가입
로그인
토큰 발급
sleep_session 생성
raw data multipart upload
```

## 1. 개발 서버 구성

개발 서버는 아래 AWS 리소스로 시작합니다.

```text
FastAPI 서버: Elastic Beanstalk Python
Database: RDS PostgreSQL dev
Raw file storage: S3 dev bucket
Logs: CloudWatch
Health check: GET /health
```

권장 이름 예시는 아래처럼 `dev`를 명확히 붙입니다.

```text
Elastic Beanstalk application: sleeptandard-api
Elastic Beanstalk environment: sleeptandard-api-dev
RDS DB identifier: sleeptandard-postgres-dev
S3 bucket: sleeptandard-raw-dev
```

## 2. 현재 프로젝트에 추가된 배포 파일

### `Procfile`

Elastic Beanstalk가 FastAPI 서버를 실행할 때 사용합니다.

```text
web: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### `.ebextensions/01_healthcheck.config`

Elastic Beanstalk health check 경로를 `/health`로 지정합니다.

```yaml
option_settings:
  aws:elasticbeanstalk:environment:process:default:
    HealthCheckPath: /health
```

### `.ebignore`

로컬 비밀값과 개발용 파일이 AWS에 올라가지 않도록 제외합니다.

특히 `.env`와 `.venv/`는 배포에 포함하지 않습니다.

## 3. AWS에서 먼저 만들 리소스

### 3.1 RDS PostgreSQL dev

개발용 PostgreSQL을 하나 만듭니다.

초기 개발 테스트 기준으로는 아래 정도면 충분합니다.

```text
Engine: PostgreSQL
Environment: dev/test
DB name: wearable_sleep
Username: wearable
Password: AWS Secrets Manager 또는 강한 비밀번호
Public access: 가능하면 비공개 권장
```

Elastic Beanstalk 서버가 RDS에 접속할 수 있도록 보안 그룹을 연결해야 합니다.

### 3.2 S3 dev bucket

raw data multipart upload 테스트용 bucket을 만듭니다.

```text
Bucket name: sleeptandard-raw-dev-062560095342-apne2
Region: ap-northeast-2 권장
Public access: Block all public access 유지
```

앱은 S3 credential을 직접 받지 않습니다. FastAPI 서버가 presigned URL만 발급합니다.

## 4. Elastic Beanstalk 환경변수

Beanstalk 환경 설정에 아래 값을 넣습니다.

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@RDS_ENDPOINT:5432/wearable_sleep
APP_NAME=Wearable Sleep API Dev
API_KEY=dev-admin-api-key-change-me
ACCESS_TOKEN_SECRET_KEY=dev-random-long-secret-change-me
ACCESS_TOKEN_EXPIRES_MINUTES=10080

AWS_REGION=ap-northeast-2
AWS_S3_ENDPOINT_URL=
S3_BUCKET_NAME=sleeptandard-raw-dev-062560095342-apne2
S3_UPLOAD_URL_EXPIRES_SEC=900
S3_MULTIPART_BACKEND=aws
PUBLIC_BASE_URL=https://DEV_ELASTIC_BEANSTALK_URL
```

주의:

```text
.env 파일은 AWS에 올리지 않습니다.
ACCESS_TOKEN_SECRET_KEY는 로컬 기본값을 그대로 쓰면 안 됩니다.
AWS access key를 환경변수에 넣지 않습니다. Elastic Beanstalk 인스턴스 역할에 최소 권한을 부여합니다.
```

## 5. IAM 권한

개발 서버가 S3 multipart upload를 제어하려면 Elastic Beanstalk 인스턴스 역할에 아래 최소 권한을 부여합니다.

```text
s3:PutObject
s3:AbortMultipartUpload
s3:ListMultipartUploadParts
```

대상 bucket은 dev bucket으로 제한합니다.

```text
arn:aws:s3:::sleeptandard-raw-dev-062560095342-apne2/users/*
```

## 6. 배포 후 DB migration

개발용 RDS가 비어 있으면 Alembic migration을 적용해야 합니다.

```bash
alembic upgrade head
```

처음에는 수동 적용으로 시작해도 됩니다.

운영 단계에서는 migration 절차를 별도로 안전하게 관리해야 합니다.

## 7. 배포 후 확인 순서

배포가 끝나면 아래 순서로 확인합니다.

```text
GET /health
GET /health/db
POST /auth/signup
POST /auth/login
GET /auth/me
POST /sleep-sessions/start
POST /v1/sleep-sessions/{session_id}/raw-uploads
```

성공 기준:

```text
/health: 200
/health/db: 200
회원가입: 201
로그인: 200
/auth/me: 200
sleep session 시작: 201
raw upload initiate: 201
```

## 8. Android 앱 연결

앱의 개발 서버 URL은 Beanstalk dev URL로 설정합니다.

```properties
SLEEP_SERVER_BASE_URL=https://DEV_ELASTIC_BEANSTALK_URL
```

앱은 raw upload 요청에서 아래 값을 직접 보내면 안 됩니다.

```text
user_id
userId
object_key
objectKey
bucket
```

서버가 토큰에서 user_id를 확인하고 S3 object key를 직접 만듭니다.

```text
users/{user_id}/sleep-sessions/{session_id}/sensor.raw.v1.bin
```

## 9. 참고 문서

- AWS Elastic Beanstalk Python platform
- AWS Elastic Beanstalk Procfile
- AWS Elastic Beanstalk requirements.txt
