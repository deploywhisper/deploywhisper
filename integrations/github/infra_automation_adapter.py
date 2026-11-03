"""Version-isolated GitHub boundary for registered infrastructure handoffs.

Workflow inputs contain correlation identifiers only. The receiver obtains its
operation-bound grant through its separately authenticated channel. GitHub
acceptance and polling never substitute for receiver consume/outcome evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

from infra_automation.contracts import SAFE_INTEGER
from infra_automation.decisions import DecisionBinding
from infra_automation.github_contracts import DispatchAcceptance, GithubRunObservation
from infra_automation.handoff import DeliveryEnvelope
from infra_automation.receiver_protocol import (
    receiver_binding_from_decision,
    validate_receiver_message,
)
from infra_automation.target_transport import (
    PinnedGithubTransport,
    TransportError,
    canonical_origin,
)
from infra_automation.targets import (
    TargetSnapshot,
    canonical,
    checked,
    semantic_payload,
)


class GithubAdapterError(RuntimeError):
    """Secret-free classification; uncertain dispatch must never be retried."""

    def __init__(self, code: str, *, may_have_sent: bool = False):
        self.code = code
        self.may_have_sent = may_have_sent
        super().__init__(code)


def _object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate GitHub key")
        value[key] = child
    return value


def _bounded(value, depth=0):
    if depth > 16:
        raise ValueError("GitHub nesting limit")
    if type(value) is dict:
        for child in value.values():
            _bounded(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _bounded(child, depth + 1)
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError("unsupported GitHub scalar")


def _json(raw):
    if type(raw) is not bytes or len(raw) > 1048576:
        raise ValueError("invalid bounded GitHub bytes")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    _bounded(value)
    return value


def _numeric_id(value):
    if type(value) is not int or not 1 <= value <= SAFE_INTEGER:
        raise ValueError("invalid GitHub numeric identity")
    return str(value)


def _sha(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("invalid GitHub revision")
    return value


class GithubInfraAutomationAdapter:
    """Validate captured identity before each fixed-origin API interaction."""

    def __init__(
        self,
        transport: PinnedGithubTransport,
        *,
        target_resolver: Callable[[str], TargetSnapshot],
        web_origins: dict[str, str] | None = None,
    ):
        self.transport = transport
        self.target_resolver = target_resolver
        self.web_origins = {"https://api.github.com": "https://github.com"}
        for api, web in (web_origins or {}).items():
            self.web_origins[canonical_origin(api)] = canonical_origin(web)

    def _get(self, snapshot, credential, resource, selector=None, *, optional=False):
        target = snapshot.definition
        response = self.transport.get_registered(
            origin=target.api_origin,
            owner=target.github_owner,
            repository=target.github_repository,
            resource=resource,
            selector=selector,
            token=credential,
            allowed_private_addresses=target.allowed_private_addresses,
        )
        if optional and response.status == 404:
            return None
        if response.status != 200:
            raise ValueError("unavailable GitHub metadata")
        return _json(response.body)

    def _identity(self, snapshot, credential):
        target = snapshot.definition
        repo = self._get(snapshot, credential, "repository")
        if (
            _numeric_id(repo["id"]) != target.pipeline_repository_id
            or repo["full_name"] != f"{target.github_owner}/{target.github_repository}"
        ):
            raise ValueError("registered repository mismatch")
        workflow = self._get(snapshot, credential, "workflow", target.github_workflow)
        if (
            _numeric_id(workflow["id"]) != target.pipeline_workflow_id
            or workflow["state"] != "active"
            or (
                not target.github_workflow.isdecimal()
                and workflow["path"] != f".github/workflows/{target.github_workflow}"
            )
        ):
            raise ValueError("registered workflow mismatch")
        if (
            target.github_workflow.isdecimal()
            and target.github_workflow != target.pipeline_workflow_id
        ):
            raise ValueError("registered workflow selector mismatch")

    @staticmethod
    def _applies(rule, ref):
        conditions = rule["conditions"]
        if type(conditions) is not dict or set(conditions) != {"ref_name"}:
            raise ValueError("unqualified ruleset conditions")
        names = conditions["ref_name"]
        if type(names) is not dict or set(names) != {"include", "exclude"}:
            raise ValueError("unqualified ruleset refs")
        for values in (names["include"], names["exclude"]):
            if type(values) is not list or len(values) > 100:
                raise ValueError("unqualified ruleset patterns")
            if any(
                type(item) is not str
                or (
                    item != "~ALL"
                    and not re.fullmatch(
                        r"refs/tags/[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", item
                    )
                )
                for item in values
            ):
                raise ValueError("unqualified ruleset pattern semantics")
        return any(item in ("~ALL", ref) for item in names["include"]) and not any(
            item in ("~ALL", ref) for item in names["exclude"]
        )

    def _tag_protected(self, snapshot, credential):
        rulesets = self._get(snapshot, credential, "rulesets")
        # Exactly-full pages might hide additional rules; do not assume completeness.
        if type(rulesets) is not list or len(rulesets) >= 100:
            raise ValueError("unqualified ruleset enumeration")
        protected_kinds = set()
        for summary in rulesets:
            rule_id = _numeric_id(summary["id"])
            rule = self._get(snapshot, credential, "ruleset", rule_id)
            if _numeric_id(rule["id"]) != rule_id:
                raise ValueError("ruleset identity mismatch")
            if rule["target"] != "tag" or rule["enforcement"] != "active":
                continue
            if not self._applies(rule, "refs/tags/" + snapshot.definition.workflow_ref):
                continue
            # A bypass principal can move/delete a supposedly immutable target.
            if rule["bypass_actors"] != []:
                raise ValueError("unqualified tag bypass")
            rules = rule["rules"]
            if type(rules) is not list or len(rules) > 100:
                raise ValueError("unqualified tag rules")
            # GitHub aggregates all applicable rulesets for the same tag.
            protected_kinds.update(item["type"] for item in rules)
        if not {"update", "deletion"}.issubset(protected_kinds):
            raise ValueError("tag update/deletion protection absent")

    def _protected_revision(self, snapshot, credential):
        if snapshot.definition.enabled is not True:
            raise ValueError("disabled target")
        self._identity(snapshot, credential)
        ref = snapshot.definition.workflow_ref
        branch = self._get(snapshot, credential, "branch", ref, optional=True)
        tag = self._get(snapshot, credential, "tag_ref", ref, optional=True)
        if (branch is None) == (tag is None):
            raise ValueError("absent or ambiguous workflow ref")
        if branch is not None:
            if branch["name"] != ref or branch["protected"] is not True:
                raise ValueError("workflow branch protection absent")
            revision = _sha(branch["commit"]["sha"])
        else:
            if tag["ref"] != "refs/tags/" + ref:
                raise ValueError("tag ref identity mismatch")
            item = tag["object"]
            seen = set()
            # Resolve annotated tags with a bounded chain and detect cycles.
            for _ in range(4):
                revision = _sha(item["sha"])
                if item["type"] == "commit":
                    break
                if item["type"] != "tag" or revision in seen:
                    raise ValueError("unqualified tag object")
                seen.add(revision)
                tag_object = self._get(snapshot, credential, "tag_object", revision)
                if tag_object["sha"] != revision:
                    raise ValueError("tag object identity mismatch")
                item = tag_object["object"]
            else:
                raise ValueError("tag resolution limit")
            self._tag_protected(snapshot, credential)
        if revision != snapshot.definition.pipeline_workflow_revision:
            raise ValueError("registered workflow revision moved")
        return revision

    def protected_revision(self, snapshot: TargetSnapshot, credential: str) -> str:
        try:
            return self._protected_revision(
                checked(snapshot, TargetSnapshot), credential
            )
        except TransportError as error:
            raise GithubAdapterError(error.code) from None
        except Exception:
            raise GithubAdapterError("github_target_unqualified") from None

    def _urls(self, snapshot, run_id, run_url, html_url):
        target = snapshot.definition
        web = self.web_origins[target.api_origin]
        path = (
            f"/{target.github_owner}/{target.github_repository}/actions/runs/{run_id}"
        )
        if run_url != target.api_origin + "/repos" + path or html_url != web + path:
            raise ValueError("uncorrelated GitHub run URL")

    def _envelope(self, envelope, snapshot):
        if not isinstance(envelope, DeliveryEnvelope):
            raise ValueError("typed envelope required")
        message = validate_receiver_message(envelope.message_bytes)
        if (
            message.operation_id != envelope.operation_id
            or message.operation != "consume"
            or message.state != "consumed"
            or message.sequence != 1
        ):
            raise ValueError("uncorrelated receiver message")
        if (
            type(envelope.payload_bytes) is not bytes
            or "sha256:" + hashlib.sha256(envelope.payload_bytes).hexdigest()
            != message.binding.payload_digest
        ):
            raise ValueError("action payload mismatch")
        payload = _json(envelope.payload_bytes)
        decision = DecisionBinding.model_validate_json(
            canonical(
                {
                    **payload["decision"],
                    "payload_digest": message.binding.payload_digest,
                }
            )
        )
        if (
            receiver_binding_from_decision(decision) != message.binding
            or semantic_payload(decision, snapshot) != envelope.payload_bytes
        ):
            raise ValueError("captured action binding mismatch")
        return message

    def dispatch(
        self, envelope: DeliveryEnvelope, credential: str
    ) -> DispatchAcceptance:
        sent = False
        post_attempted = False
        try:
            snapshot = checked(
                self.target_resolver(envelope.operation_id), TargetSnapshot
            )
            if snapshot.definition.api_origin not in self.web_origins:
                raise ValueError("registered API lacks a qualified web origin")
            message = self._envelope(envelope, snapshot)
            self._protected_revision(snapshot, credential)
            target = snapshot.definition
            post_attempted = True
            response = self.transport.post_registered(
                origin=target.api_origin,
                owner=target.github_owner,
                repository=target.github_repository,
                workflow=target.github_workflow,
                payload_bytes=canonical(
                    {
                        "ref": target.workflow_ref,
                        "inputs": {
                            "operation_id": envelope.operation_id,
                            "binding_digest": message.binding_digest,
                        },
                    }
                ),
                token=credential,
                allowed_private_addresses=target.allowed_private_addresses,
            )
            sent = True
            if response.status != 200:
                raise ValueError("dispatch acceptance not established")
            value = _json(response.body)
            if type(value) is not dict or set(value) != {
                "workflow_run_id",
                "run_url",
                "html_url",
            }:
                raise ValueError("unqualified dispatch acceptance")
            run_id = int(_numeric_id(value["workflow_run_id"]))
            self._urls(snapshot, run_id, value["run_url"], value["html_url"])
            return DispatchAcceptance(
                operation_id=envelope.operation_id,
                binding_digest=message.binding_digest,
                repository_id=target.pipeline_repository_id,
                workflow_id=target.pipeline_workflow_id,
                workflow_revision=target.pipeline_workflow_revision,
                workflow_ref=target.workflow_ref,
                run_id=run_id,
                run_url=value["run_url"],
                html_url=value["html_url"],
            )
        except TransportError as error:
            raise GithubAdapterError(
                error.code,
                may_have_sent=sent or (post_attempted and error.may_have_sent),
            ) from None
        except Exception:
            raise GithubAdapterError(
                "github_dispatch_unqualified", may_have_sent=sent or post_attempted
            ) from None

    def poll(
        self, snapshot: TargetSnapshot, acceptance: DispatchAcceptance, credential: str
    ) -> GithubRunObservation:
        try:
            snapshot = checked(snapshot, TargetSnapshot)
            acceptance = checked(acceptance, DispatchAcceptance)
            target = snapshot.definition
            if (
                acceptance.repository_id,
                acceptance.workflow_id,
                acceptance.workflow_revision,
                acceptance.workflow_ref,
            ) != (
                target.pipeline_repository_id,
                target.pipeline_workflow_id,
                target.pipeline_workflow_revision,
                target.workflow_ref,
            ):
                raise ValueError("accepted target mismatch")
            self._urls(
                snapshot, acceptance.run_id, acceptance.run_url, acceptance.html_url
            )
            # Reading the already accepted run remains available after target
            # revocation/ref movement. Only the captured immutable run identity
            # is relevant here; admission separately calls protected_revision.
            run = self._get(snapshot, credential, "run", str(acceptance.run_id))
            if (
                _numeric_id(run["id"]) != str(acceptance.run_id)
                or _numeric_id(run["workflow_id"]) != target.pipeline_workflow_id
                or _numeric_id(run["repository"]["id"]) != target.pipeline_repository_id
                or run["repository"]["full_name"]
                != f"{target.github_owner}/{target.github_repository}"
                or _sha(run["head_sha"]) != target.pipeline_workflow_revision
                or run["head_branch"] != target.workflow_ref
                or run["event"] != "workflow_dispatch"
            ):
                raise ValueError("uncorrelated workflow run")
            self._urls(snapshot, acceptance.run_id, run["url"], run["html_url"])
            return GithubRunObservation(
                run_id=acceptance.run_id,
                repository_id=target.pipeline_repository_id,
                workflow_id=target.pipeline_workflow_id,
                workflow_revision=target.pipeline_workflow_revision,
                workflow_ref=target.workflow_ref,
                run_url=run["url"],
                html_url=run["html_url"],
                status=run["status"],
                conclusion=run["conclusion"],
            )
        except TransportError as error:
            raise GithubAdapterError(error.code) from None
        except Exception:
            raise GithubAdapterError("github_poll_unqualified") from None
