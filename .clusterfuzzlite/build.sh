#!/bin/bash
set -euo pipefail

target=content_security_fuzzer
pyinstaller --distpath "$OUT" --workpath "$WORK/pyinstaller" \
  --specpath "$WORK" --paths "$SRC/deploywhisper" --onefile \
  --name "$target.pkg" ".clusterfuzzlite/$target.py"
# Only the wrapper should be discovered as a fuzz target. These Python paths
# use the built-in Atheris engine; they do not require native sanitizer preload.
chmod -x "$OUT/$target.pkg"
cat > "$OUT/$target" <<'WRAPPER'
#!/bin/sh
# LLVMFuzzerTestOneInput for fuzzer detection.
set -eu
this_dir=$(dirname "$0")
chmod +x "$this_dir/content_security_fuzzer.pkg"
exec "$this_dir/content_security_fuzzer.pkg" "$@"
WRAPPER
chmod +x "$OUT/$target"
cp ".clusterfuzzlite/$target.options" "$OUT/"
python3 - "$OUT/${target}_seed_corpus.zip" <<'PY'
import pathlib
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as archive:
    for seed in sorted(pathlib.Path(".clusterfuzzlite/corpus").iterdir()):
        archive.write(seed, seed.name)
PY
