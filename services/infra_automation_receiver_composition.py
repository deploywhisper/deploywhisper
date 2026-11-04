"""Explicit trusted composition of the GitHub carrier and admitted decision core.

Constructing a carrier is not material qualification. The supplied decision
service must retain its own live scoped material witness; its default denies.
No HTTP request can select a service, transport, resolver or origin mapping.
"""

from __future__ import annotations

import config
from infra_automation.lifecycle import LifecycleError
from infra_automation.target_transport import PinnedGithubTransport
from integrations.github.infra_automation_adapter import GithubInfraAutomationAdapter
from services import project_service as authorization
from services.infra_automation_handoffs import HandoffService


def create_github_handoff_service(
    *,
    decision_service,
    session_factory=None,
    clock=None,
    web_origins=None,
    _transport=None,
):
    """Bind trusted ports without enabling a collector or inventing authority."""
    service = HandoffService(
        decision_service=decision_service,
        session_factory=session_factory,
        clock=clock,
    )

    def target_for_operation(operation_id):
        with authorization.authorized_session(
            session_factory=session_factory
        ) as session:
            row, _, _, snapshot = service._load(session, operation_id)
            if row.broken:
                raise LifecycleError(409)
            return snapshot

    transport = _transport or PinnedGithubTransport(
        allowed_origins=config.handoff_allowed_origins()
    )
    adapter = GithubInfraAutomationAdapter(
        transport, target_resolver=target_for_operation, web_origins=web_origins
    )

    def credential(snapshot):
        try:
            token = config.handoff_credentials("dispatch").get(
                snapshot.definition.credential_ref
            )
        except (ValueError, TypeError):
            raise LifecycleError(503) from None
        if type(token) is not str or not token:
            raise LifecycleError(503)
        return token

    service.ref_port = lambda snapshot: adapter.protected_revision(
        snapshot, credential(snapshot)
    )
    service.delivery_port = adapter.dispatch
    service.observation_port = lambda acceptance, snapshot: adapter.poll(
        snapshot, acceptance, credential(snapshot)
    )
    return service
