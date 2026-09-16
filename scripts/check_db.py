import sys
from pathlib import Path

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        result = db.execute(text("SELECT 1")).scalar_one()
        tables = db.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
        ).scalars()
        print({"db": result, "tables": list(tables)})


if __name__ == "__main__":
    main()
