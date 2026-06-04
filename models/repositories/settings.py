"""Settings repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.tables import AppSetting


def upsert_setting(session: Session, *, key: str, value: str) -> AppSetting:
    record = session.get(AppSetting, key)
    if record is None:
        record = AppSetting(key=key, value=value)
        session.add(record)
    else:
        record.value = value
    session.commit()
    session.refresh(record)
    return record


def get_setting(session: Session, key: str) -> AppSetting | None:
    return session.get(AppSetting, key)


def list_settings(session: Session) -> list[AppSetting]:
    return session.query(AppSetting).order_by(AppSetting.key.asc()).all()


def delete_setting(session: Session, key: str) -> None:
    record = session.get(AppSetting, key)
    if record is None:
        return
    session.delete(record)
    session.commit()


def delete_settings_by_key_prefix(session: Session, prefix: str) -> int:
    records = session.query(AppSetting).filter(AppSetting.key.like(f"{prefix}%")).all()
    for record in records:
        session.delete(record)
    session.commit()
    return len(records)
