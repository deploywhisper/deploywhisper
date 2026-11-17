"""Independent trusted test authorization and minimal cloud storage schema."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from models.database import Base
from models.tables import (
    Project,
    ProjectWorkspace,
    AppSetting,
    AnalysisReport,
    Finding,
    EvidenceItem,
    RiskAssessment,
)


class ReferenceFixture:
    """A server-installed synthetic authority, never a production auth adapter."""

    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + str(Path(self.temp.name) / "reference.db")
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(
            self.engine,
            tables=[
                model.__table__
                for model in (
                    Project,
                    ProjectWorkspace,
                    AppSetting,
                    AnalysisReport,
                    Finding,
                    EvidenceItem,
                    RiskAssessment,
                )
            ],
        )
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.factory() as session:
            session.add(
                Project(id=1, project_key="reference", display_name="Reference")
            )
            session.commit()
        self.now = datetime.now(timezone.utc) - timedelta(seconds=1)

    @contextmanager
    def session(self, project_id, operation):
        with self.factory() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                self.check(session, project_id, operation)
                yield session
                self.check(session, project_id, operation)
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def check(self, session, project_id, operation):
        if project_id != 1 or operation not in {
            "configure",
            "collect",
            "read",
            "admit",
            "purge",
        }:
            raise PermissionError("reference fixture scope denied")

    def close(self):
        self.engine.dispose()
        self.temp.cleanup()
