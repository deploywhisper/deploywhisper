"""Settings repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.tables import AppSetting


def upsert_setting(
    session: Session, *, key: str, value: str, commit: bool = True
) -> AppSetting:
    record = session.get(AppSetting, key)
    if record is None:
        record = AppSetting(key=key, value=value)
        session.add(record)
    else:
        record.value = value
    session.commit() if commit else session.flush()
    session.refresh(record)
    return record


def get_setting(session: Session, key: str) -> AppSetting | None:
    return session.get(AppSetting, key)


def list_settings(session: Session) -> list[AppSetting]:
    return session.query(AppSetting).order_by(AppSetting.key.asc()).all()


def delete_setting(session: Session, key: str, *, commit: bool = True) -> None:
    record = session.get(AppSetting, key)
    if record is None:
        return
    session.delete(record)
    session.commit() if commit else session.flush()


def delete_settings_by_key_prefix(
    session: Session, prefix: str, *, commit: bool = True
) -> int:
    records = session.query(AppSetting).filter(AppSetting.key.like(f"{prefix}%")).all()
    for record in records:
        session.delete(record)
    session.commit() if commit else session.flush()
    return len(records)
