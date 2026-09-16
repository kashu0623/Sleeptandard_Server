from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import register_exception_handlers
from app.routers.auth import router as auth_router
from app.routers.devices import router as devices_router
from app.routers.raw_uploads import router as raw_uploads_router
from app.routers.sleep_sessions import router as sleep_sessions_router
from app.routers.users import router as users_router


settings = get_settings()

openapi_tags = [
    {
        "name": "health",
        "description": "서버와 PostgreSQL 연결 상태를 확인합니다.",
    },
    {
        "name": "auth",
        "description": "앱 회원가입, 로그인, 현재 로그인 사용자 확인을 다룹니다.",
    },
    {
        "name": "users",
        "description": "베타 호환 사용자 등록, 조회, 사용자별 수면 기록 목록을 다룹니다.",
    },
    {
        "name": "devices",
        "description": "웨어러블 기기 등록과 조회를 다룹니다.",
    },
    {
        "name": "sleep_sessions",
        "description": "수면 측정 시작, 종료, 중단, 알람, 요약, 파일 상태, 상세 조회를 다룹니다.",
    },
    {
        "name": "raw_uploads",
        "description": "Potch raw 파일의 S3 multipart 업로드 흐름을 다룹니다.",
    },
]

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="웨어러블 수면 베타 v1용 로컬 FastAPI 백엔드입니다.",
    openapi_tags=openapi_tags,
)
register_exception_handlers(app)
app.include_router(auth_router)
app.include_router(devices_router)
app.include_router(raw_uploads_router)
app.include_router(sleep_sessions_router)
app.include_router(users_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
def health_db(db: Session = Depends(get_db)) -> dict[str, str | int]:
    value = db.execute(text("SELECT 1")).scalar_one()
    return {"status": "ok", "db": value}
