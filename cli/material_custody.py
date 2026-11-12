"""Serve live signed custody checks from the privileged authority process."""

from __future__ import annotations

import argparse
import sys

from infra_automation.material_authority import load_private_key
from infra_automation.material_probe import MaterialCustodyProbeServer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--custody-root", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--socket-gid", type=int)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    try:
        with MaterialCustodyProbeServer(
            args.socket,
            args.custody_root,
            load_private_key(args.private_key),
            socket_gid=args.socket_gid,
        ) as server:
            if args.once:
                return 0 if server.serve_once() else 1
            while True:
                try:
                    server.serve_once()
                except TimeoutError:
                    continue
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError):
        print("Material custody probe unavailable.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
