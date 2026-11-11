"""Operator-local publication of nonsecret co-located material authority."""

from __future__ import annotations

import argparse
import json
import sys

import config
from infra_automation.material_authority import (
    MaterialAuthorityDocument,
    MaterialAuthorityLedger,
    load_private_key,
    load_public_key,
)
from infra_automation.lifecycle import LifecycleError
from infra_automation.receiver_custody import ProtectedCustody
from models.database import SessionLocal
from models.repositories import infra_automation_runs as runs
from services import project_service as authorization
from services.infra_automation_material_authority import CoLocatedMaterialAuthority


def _custody_probe(custody):
    def verify(record, collection, binding):
        with custody.verify(binding) as artifact:
            return bool(
                artifact.metadata.get("handle") == record.custody_handle
                and artifact.metadata.get("raw_local_digest") == record.raw_local_digest
                and artifact.metadata.get("source")
                == binding.provenance.source.model_dump(mode="json")
            )

    return verify


def _current_document(ledger, status):
    try:
        return ledger.read(
            source_id=status["installation_id"],
            recovery_generation=status["generation"],
        )
    except FileNotFoundError:
        return MaterialAuthorityDocument(
            source_id=status["installation_id"],
            recovery_generation=status["generation"],
        )
    except ValueError:
        previous = ledger.read_any()
        if status["generation"] <= previous.recovery_generation:
            raise
        rebound = MaterialAuthorityDocument(
            source_id=status["installation_id"],
            recovery_generation=status["generation"],
            records=tuple(
                row.model_copy(
                    update={"state": "revoked", "generation": row.generation + 1}
                )
                for row in previous.records
            ),
        )
        ledger.write(rebound)
        return rebound


def prepare(run_id, step_id, generation=None):
    from infra_automation.operator_recovery import configured_store

    if (
        config.settings.material_authority_profile != "colocated-v1"
        or not config.settings.material_ledger_path
    ):
        raise ValueError("Co-located material authority is not configured")
    store = configured_store()
    if store is None:
        raise ValueError("Operator recovery control is not configured")
    status = store.assert_ready(effects=True)
    custody_root = config.settings.material_custody_root
    if not custody_root:
        raise ValueError("Separate protected material custody root is not configured")
    if (
        not config.settings.material_signing_key_path
        or not config.settings.material_verification_key_path
    ):
        raise ValueError("Material authority signing keys are not configured")
    ledger = MaterialAuthorityLedger(
        config.settings.material_ledger_path,
        signing_key=load_private_key(config.settings.material_signing_key_path),
        verification_key=load_public_key(
            config.settings.material_verification_key_path
        ),
    )
    current = _current_document(ledger, status)
    maximum = max((row.generation for row in current.records), default=0)
    selected_generation = maximum + 1 if generation is None else generation
    if selected_generation <= maximum:
        raise ValueError("Material generation must exceed the retained maximum")
    authority = CoLocatedMaterialAuthority(
        config.settings.material_ledger_path,
        verification_key=load_public_key(
            config.settings.material_verification_key_path
        ),
        recovery_status=lambda session: status,
        custody_probe=_custody_probe(ProtectedCustody(custody_root)),
    )
    with authorization.authorized_session(SessionLocal) as session:
        run = runs.get_run(session, run_id)
        if run is None:
            raise ValueError("Run is unavailable")
        proposed = authority.propose_record(session, run, step_id, selected_generation)
    retained = tuple(
        row
        for row in current.records
        if (row.run_id, row.step_id) != (proposed.run_id, proposed.step_id)
    )
    document = current.model_copy(update={"records": (*retained, proposed)})
    ledger.write(document)
    return {
        "run_id": proposed.run_id,
        "step_id": proposed.step_id,
        "binding_digest": proposed.binding_digest,
        "generation": proposed.generation,
        "source_id": document.source_id,
        "recovery_generation": document.recovery_generation,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--generation", type=int)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.run_id, args.step_id, args.generation)
    except (ValueError, OSError, LifecycleError):
        print("Material authority publication unavailable.", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
