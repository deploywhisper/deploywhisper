"""Private transaction-bound report read during authenticated receiver admission.

The handoff service binds this only after independent receiver/grant checks.
It issues no human principal, project capability, session or reusable credential.
The supplied reader repeats operation-bound receiver verification for each read.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Iterator

from sqlalchemy.orm import Session
from models.tables import AnalysisReport


@dataclass(frozen=True, repr=False)
class _ReceiverReportRead:
    session: Session
    transaction: object
    reader: Callable[[Session, int], AnalysisReport]


_current: ContextVar[_ReceiverReportRead | None] = ContextVar(
    "private_receiver_report_read", default=None
)


def has_receiver_report_read() -> bool:
    return _current.get() is not None


@contextmanager
def _bind_receiver_report(
    session: Session, reader: Callable[[Session, int], AnalysisReport]
) -> Iterator[None]:
    from services import project_service as authorization

    authorization._require_operation(session)
    if not callable(reader):
        raise authorization.TrustedAuthorizationError()
    token = _current.set(
        _ReceiverReportRead(session, session.get_transaction(), reader)
    )
    try:
        yield
    finally:
        _current.reset(token)


def read_receiver_report(
    session: Session, report_id: int, capability: str, *, mutation: bool | None = None
) -> AnalysisReport:
    from services import project_service as authorization

    authorization._require_operation(session)
    bound = _current.get()
    if (
        bound is None
        or bound.session is not session
        or bound.transaction is not session.get_transaction()
        or capability != "report.read"
        or mutation is True
        or type(report_id) is not int
        or report_id < 1
    ):
        raise authorization.TrustedAuthorizationError()
    row = bound.reader(session, report_id)
    if not isinstance(row, AnalysisReport) or row.id != report_id:
        raise authorization.TrustedAuthorizationError()
    return row
