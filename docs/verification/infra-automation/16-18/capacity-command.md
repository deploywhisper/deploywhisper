# Reproduce the bounded Linux capacity measurement

Run from the frozen repository revision with Docker already installed. Use fresh
test resources and the exact image below; no deployment database, `.env`, receiver
secret or Docker socket is mounted. The runtime image excludes development test
helpers, so only the listed source paths are mounted read-only.

```sh
capacity_image=sha256:363f797bb98e1ca90f549892b28802d6589000e776505a6f21cefdc7e61c41df
capacity_container=dw16-18-capacity-example
capacity_volume=dw16-18-capacity-example-evidence
docker volume create --label purpose=story16-18-disposable-capacity "$capacity_volume"
docker run --rm --network none --user 0:0 --entrypoint python \
  -v "$capacity_volume:/evidence" "$capacity_image" \
  -c 'import os; os.chown("/evidence",999,999); os.chmod("/evidence",0o700)'
docker run --name "$capacity_container" --network none --cpus 2 \
  --memory 2g --memory-swap 2g --pids-limit 128 --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=268435456,mode=1777 --user 999:999 \
  --entrypoint python -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app \
  -v "$capacity_volume:/evidence" \
  -v "$PWD/scripts:/app/scripts:ro" -v "$PWD/tests:/app/tests:ro" \
  -v "$PWD/api_server.py:/app/api_server.py:ro" -v "$PWD/cli.py:/app/cli.py:ro" \
  "$capacity_image" scripts/qualify_operator_capacity.py \
  --output /evidence --seconds 1800
mkdir -p docs/verification/infra-automation/16-18/capacity
docker cp "$capacity_container:/evidence/." docs/verification/infra-automation/16-18/capacity/
docker rm "$capacity_container"
docker volume rm "$capacity_volume"
```

The preparation container only assigns ownership of the new evidence volume.
The measured process runs as UID/GID 999 with two CPU cores, 2 GiB memory, a
256 MiB temporary filesystem and no network. All database/control/artifact/custody
fixtures live in private temporary directories. Application recovery controls
are configured, and spawned workers inherit the same bound control directory.

This measures ten active runs, at most two actual spawned **synthetic** analysis
workers, and twenty enrolled, redeemed, polled authenticated local runner service
ports. It does not substitute for twenty remote HTTPS runner processes, real
collector workloads, production receivers or host-power-loss qualification.
The report includes real elapsed monotonic time, rotations, queue backpressure,
resource/error observations, schema and before/after source witnesses. A smoke
run uses `--smoke --seconds 15` and is explicitly unqualified.

The final run's result is reported in `capacity/operator-capacity.json` and
`capacity/container-profile.json`. Interrupted measurements in the adjacent
`capacity-*` directories are retained as unqualified development evidence.
