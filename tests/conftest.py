from collections.abc import Iterator

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal


def cleanup_test_data() -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                """
                DELETE FROM sleep_session_uploads
                USING sleep_sessions, users
                WHERE sleep_session_uploads.session_id = sleep_sessions.id
                  AND sleep_sessions.user_id = users.id
                  AND (
                    users.beta_code LIKE 'TEST_%'
                    OR users.email LIKE 'test-auth-%@example.com'
                  )
                """
            )
        )
        db.execute(
            text(
                """
                DELETE FROM alarm_events
                USING sleep_sessions, users
                WHERE alarm_events.sleep_session_id = sleep_sessions.id
                  AND sleep_sessions.user_id = users.id
                  AND (
                    users.beta_code LIKE 'TEST_%'
                    OR users.email LIKE 'test-auth-%@example.com'
                  )
                """
            )
        )
        db.execute(
            text(
                """
                DELETE FROM sleep_summaries
                USING sleep_sessions, users
                WHERE sleep_summaries.sleep_session_id = sleep_sessions.id
                  AND sleep_sessions.user_id = users.id
                  AND (
                    users.beta_code LIKE 'TEST_%'
                    OR users.email LIKE 'test-auth-%@example.com'
                  )
                """
            )
        )
        db.execute(
            text(
                """
                DELETE FROM sleep_sessions
                USING users
                WHERE sleep_sessions.user_id = users.id
                  AND (
                    users.beta_code LIKE 'TEST_%'
                    OR users.email LIKE 'test-auth-%@example.com'
                  )
                """
            )
        )
        db.execute(text("DELETE FROM devices WHERE device_code LIKE 'TEST_%'"))
        db.execute(text("DELETE FROM users WHERE beta_code LIKE 'TEST_%'"))
        db.execute(text("DELETE FROM users WHERE email LIKE 'test-auth-%@example.com'"))
        db.commit()


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    cleanup_test_data()
    yield
    cleanup_test_data()
