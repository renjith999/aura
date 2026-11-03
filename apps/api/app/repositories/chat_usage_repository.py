from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import DateTime, bindparam, text
from sqlalchemy.orm import Session

from app.models.chat_usage import ChatUsageWindow

_TABLE_NAME = ChatUsageWindow.__tablename__
_UPSERT_CHAT_USAGE = text(
    f"""
        INSERT INTO {_TABLE_NAME} (user_id, window_started_at, request_count)
        VALUES (:user_id, :now, 1)
        ON CONFLICT (user_id) DO UPDATE SET
            window_started_at = CASE
                WHEN {_TABLE_NAME}.window_started_at <= :expired_before THEN :now
                ELSE {_TABLE_NAME}.window_started_at
            END,
            request_count = CASE
                WHEN {_TABLE_NAME}.window_started_at <= :expired_before THEN 1
                WHEN {_TABLE_NAME}.request_count <= :limit
                    THEN {_TABLE_NAME}.request_count + 1
                ELSE {_TABLE_NAME}.request_count
            END
        RETURNING request_count, window_started_at
        """
).bindparams(
    bindparam("now", type_=DateTime(timezone=True)),
    bindparam("expired_before", type_=DateTime(timezone=True)),
)


class ChatUsageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def consume_request(
        self,
        user_id: str,
        now: datetime,
        limit: int,
        window_seconds: int,
    ) -> int | None:
        expired_before = now - timedelta(seconds=window_seconds)
        row = self.session.execute(
            _UPSERT_CHAT_USAGE,
            {
                "user_id": user_id,
                "now": now,
                "expired_before": expired_before,
                "limit": limit,
            },
        ).one()
        self.session.commit()

        if row.request_count <= limit:
            return None

        window_started_at = _as_utc_datetime(row.window_started_at)
        retry_after = ceil(
            (
                window_started_at + timedelta(seconds=window_seconds) - now
            ).total_seconds()
        )
        return max(1, retry_after)


def _as_utc_datetime(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
