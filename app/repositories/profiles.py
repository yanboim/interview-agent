"""Owner-scoped user profile persistence slice."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select, update

from app.database import user_profiles


class ProfileRepositoryMixin:
    engine: Any

    def initialize(self) -> None: ...

    def get_user_profile(self, *, user_id: str) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().first()
        return dict(row) if row else None

    def upsert_user_profile(
        self,
        *,
        user_id: str,
        target_role: str,
        experience_level: str,
        focus_areas: str,
        interview_date: str | None,
        job_description: str,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = {
            "target_role": target_role,
            "experience_level": experience_level,
            "focus_areas": focus_areas,
            "interview_date": interview_date or None,
            "job_description": job_description,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            result = connection.execute(
                update(user_profiles)
                .where(user_profiles.c.user_id == user_id)
                .values(**values)
            )
            if not result.rowcount:
                connection.execute(
                    insert(user_profiles).values(
                        user_id=user_id,
                        created_at=now,
                        **values,
                    )
                )
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().one()
        return dict(row)
    def update_reminder_preferences(
        self,
        *,
        user_id: str,
        enabled: bool,
        reminder_time: str,
        timezone: str,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = {
            "reminder_enabled": enabled,
            "reminder_time": reminder_time,
            "reminder_timezone": timezone,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            result = connection.execute(
                update(user_profiles)
                .where(user_profiles.c.user_id == user_id)
                .values(**values)
            )
            if not result.rowcount:
                connection.execute(
                    insert(user_profiles).values(
                        user_id=user_id,
                        target_role="",
                        experience_level="高级",
                        focus_areas="",
                        job_description="",
                        created_at=now,
                        **values,
                    )
                )
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().one()
        return dict(row)

    def update_profile_avatar(
        self,
        *,
        user_id: str,
        avatar_data_url: str | None,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = {
            "avatar_data_url": avatar_data_url,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            result = connection.execute(
                update(user_profiles)
                .where(user_profiles.c.user_id == user_id)
                .values(**values)
            )
            if not result.rowcount:
                connection.execute(
                    insert(user_profiles).values(
                        user_id=user_id,
                        target_role="",
                        experience_level="高级",
                        focus_areas="",
                        job_description="",
                        created_at=now,
                        **values,
                    )
                )
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().one()
        return dict(row)

