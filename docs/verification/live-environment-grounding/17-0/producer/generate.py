"""Generate synthetic local-only plans with real producers; never contacts AWS."""

from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import platform
import subprocess
import tempfile
from urllib.parse import urljoin, urlsplit
import zipfile

BASE = Path(__file__).resolve().parent
PROFILES = [
    ("terraform", "1.17.2"),
    ("terraform", "1.16.7"),
    ("tofu", "1.13.9"),
    ("tofu", "1.12.12"),
]
INITIAL = """resource "terraform_data" "changed" { input = "before" }
resource "terraform_data" "removed" { input = "remove-me" }
module "nested" { source = "./nested" }
"""
UPDATED = """resource "terraform_data" "changed" { input = "after" }
resource "terraform_data" "created" { input = "new" }
module "nested" { source = "./nested" }
"""


def download(url, path):
    allowed_hosts = {
        "releases.hashicorp.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    for _ in range(6):
        target = urlsplit(url)
        if (
            target.scheme != "https"
            or target.hostname not in allowed_hosts
            or target.port not in {None, 443}
            or target.username is not None
            or target.password is not None
        ):
            raise ValueError("noncanonical producer download URL")
        connection = http.client.HTTPSConnection(target.hostname, timeout=60)
        try:
            request_path = target.path + ("?" + target.query if target.query else "")
            connection.request(
                "GET",
                request_path,
                headers={"User-Agent": "DeployWhisper-17.0-qualification"},
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise RuntimeError("missing producer redirect URL")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise RuntimeError(f"producer download HTTP {response.status}")
            path.write_bytes(response.read())
            return
        finally:
            connection.close()
    raise RuntimeError("too many producer download redirects")


def project(plan):
    """Keep only synthetic identity/input fields, not complete producer outputs/state."""

    def module_projection(module):
        return {
            "resources": [
                {
                    "address": row["address"],
                    "mode": row["mode"],
                    "type": row["type"],
                    "name": row["name"],
                    "values": {key: row["values"].get(key) for key in ("id", "input")},
                }
                for row in module.get("resources", [])
            ],
            "child_modules": [
                module_projection(child) for child in module.get("child_modules", [])
            ],
        }

    def values_projection(value):
        return {key: value.get(key) for key in ("id", "input")} if value else None

    return {
        "format_version": plan["format_version"],
        "terraform_version": plan["terraform_version"],
        "prior_state": {
            "format_version": plan["prior_state"]["format_version"],
            "values": {
                "root_module": module_projection(
                    plan["prior_state"]["values"]["root_module"]
                )
            },
        },
        "resource_changes": [
            {
                "address": row["address"],
                "mode": row["mode"],
                "type": row["type"],
                "name": row["name"],
                "change": {
                    "actions": row["change"]["actions"],
                    "before": values_projection(row["change"].get("before")),
                    "after": values_projection(row["change"].get("after")),
                },
            }
            for row in plan["resource_changes"]
        ],
    }


def main():
    records = []
    for tool, version in PROFILES:
        stem = f"{tool}_{version}"
        prefix = (
            f"https://releases.hashicorp.com/terraform/{version}/"
            if tool == "terraform"
            else f"https://github.com/opentofu/opentofu/releases/download/v{version}/"
        )
        archive_name = stem + "_darwin_arm64.zip"
        with tempfile.TemporaryDirectory(prefix="dw17-producer-") as temporary:
            root = Path(temporary)
            archive = root / archive_name
            sums = root / "SHA256SUMS"
            download(prefix + archive_name, archive)
            download(prefix + stem + "_SHA256SUMS", sums)
            expected = next(
                line.split()[0]
                for line in sums.read_text().splitlines()
                if line.split()[-1] == archive_name
            )
            observed = hashlib.sha256(archive.read_bytes()).hexdigest()
            if expected != observed:
                raise RuntimeError("official release checksum mismatch")
            with zipfile.ZipFile(archive) as bundle:
                binary = root / tool
                binary.write_bytes(bundle.read(tool))
            binary.chmod(0o700)
            work = root / "work"
            work.mkdir()
            (work / "nested").mkdir()
            (work / "nested/main.tf").write_text(
                'resource "terraform_data" "nested" { input = "nested-before" }\n'
            )
            (work / "main.tf").write_text(INITIAL)
            environment = {
                "HOME": str(root),
                "PATH": "/usr/bin:/bin",
                "TF_IN_AUTOMATION": "1",
                "CHECKPOINT_DISABLE": "1",
            }
            commands = []

            def run(*args):
                command = [str(binary), *args]
                result = subprocess.run(
                    command,
                    cwd=work,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    check=True,
                )
                commands.append([tool, *args])
                return result.stdout

            producer_version = json.loads(run("version", "-json"))
            run("init", "-backend=false", "-input=false", "-no-color")
            # Only built-in terraform_data, no cloud providers: creates local synthetic state.
            run("apply", "-auto-approve", "-input=false", "-no-color")
            (work / "main.tf").write_text(UPDATED)
            (work / "nested/main.tf").write_text(
                'resource "terraform_data" "nested" { input = "nested-after" }\n'
            )
            run(
                "plan",
                "-refresh=false",
                "-input=false",
                "-no-color",
                "-out=synthetic.plan",
            )
            raw_plan = json.loads(run("show", "-json", "synthetic.plan"))
            projected = project(raw_plan)
            output = BASE / f"{tool}-{version}.json"
            output.write_text(json.dumps(projected, indent=2) + "\n")
            records.append(
                {
                    "tool": tool,
                    "version": version,
                    "reported_version": producer_version["terraform_version"],
                    "format_version": projected["format_version"],
                    "prior_state_format_version": projected["prior_state"][
                        "format_version"
                    ],
                    "archive_url": prefix + archive_name,
                    "checksums_url": prefix + stem + "_SHA256SUMS",
                    "archive_sha256": observed,
                    "commands": commands,
                    "fixture": str(output.relative_to(BASE.parent)),
                    "fixture_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }
            )
    result = {
        "scope": "Real producer JSON shape qualification using synthetic local builtin terraform_data only; no AWS provider or credential use. Raw state and binary plans discarded with temporary directories.",
        "hardware": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "generation_command": "./.venv/bin/python docs/verification/live-environment-grounding/17-0/producer/generate.py",
        "profiles": records,
        "limitations": [
            "Checksum verification uses official HTTPS checksum manifests, not independent signature verification.",
            "Built-in terraform_data validates producer JSON prior-state layout, not AWS provider schema correctness.",
            "Supported plan format is only actual observed version(s); synthetic 1.0/1.1 shape probes elsewhere are not producer compatibility proof.",
        ],
    }
    (BASE.parent / "producer-results.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "profiles": len(records),
                "formats": sorted({row["format_version"] for row in records}),
            }
        )
    )


if __name__ == "__main__":
    main()
