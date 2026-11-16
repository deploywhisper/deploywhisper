"""Run the cloud/evidence shard without provider SDKs, other epic code or network."""

from __future__ import annotations

import importlib.abc
from pathlib import Path
import socket
import sys
import unittest


def forbidden(name: str) -> bool:
    return name.startswith("services.infra_automation") or any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in ("infra_automation", "boto3", "botocore", "azure", "google.cloud")
    )


class IsolatedImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if forbidden(fullname):
            raise AssertionError("Cloud isolation forbids dependency: " + fullname)
        return None


def no_network(*args, **kwargs):
    raise AssertionError("Cloud isolation forbids network access")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    for source in (root / "cloud").rglob("*.py"):
        if "infra_automation" in source.read_text():
            raise AssertionError(
                "Cloud source violates the independent import boundary"
            )
    if any(forbidden(name) for name in sys.modules):
        raise AssertionError("Cloud isolation requires a fresh interpreter")
    sys.path.insert(0, str(root))
    sys.meta_path.insert(0, IsolatedImports())
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.socket.sendto = no_network
    socket.create_connection = no_network
    socket.getaddrinfo = no_network
    suite = unittest.TestSuite()
    for target in ("test_cloud", "test_evidence"):
        suite.addTests(
            unittest.defaultTestLoader.discover(
                str(root / "tests" / target), top_level_dir=str(root)
            )
        )
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromName(
            "tests.test_models.test_cloud_snapshot_storage"
        )
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
