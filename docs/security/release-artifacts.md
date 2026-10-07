# Exact-source release artifacts

The `Signed Release Artifacts` workflow builds a source archive from the exact
`github.sha`, rather than the checkout's working files. Git supplies deterministic
tar headers and Python writes gzip with no filename or timestamp (`gzip -n`
semantics). `source-manifest.json` records the commit, ref, repository, release
label, packaging version and archive SHA-256. `SHA256SUMS` covers the archive and
manifest. The pinned `actions/attest` action signs all three assets with native
SLSA provenance. Its signed JSONL bundle is copied byte-for-byte to
`artifact.intoto.jsonl`; it is not a hand-written provenance claim.

Manual previews are restricted to `develop`, which must be the default branch.
The source SHA must be on that branch. The preview label contains the full commit
SHA, and workflow artifacts are retained for 30 days. This path creates no public
release, tag, container image or stable alias. A preview does not establish a
public Signed-Releases result, and historical unsigned releases stay unchanged.

The release pipeline calls this reusable workflow with a matching version tag.
The caller's SHA/ref remain the provenance source; the reusable workflow is the
signer identity. Stable and RC versions must match source packaging metadata:
`v1.4.0-rc.1` requires `1.4.0rc1` or `1.4.0-rc.1`, and cannot match `1.4.0`.
The owner authorized stable `v1.4.0` on 2026-10-07. Publication still requires the full release pipeline gates; an artifact preview alone is insufficient.

## Reproduce locally

No runtime packages are needed:

```sh
SOURCE_SHA=$(git rev-parse HEAD)
python3 -m scripts.release_artifacts build \
  --source-sha "$SOURCE_SHA" --source-ref refs/heads/develop \
  --release "preview-$SOURCE_SHA" --repository deploywhisper/deploywhisper \
  --output-dir /tmp/deploywhisper-source-assets
```

Use an empty output directory. A local build has no cryptographic attestation;
signing requires the trusted GitHub Actions job's OIDC identity.

## Verify downloaded assets

Download a workflow artifact using `gh run download RUN_ID --repo REPOSITORY
--name ARTIFACT_NAME`, or obtain the archive and bundle from an approved public
release. Obtain the expected commit and ref independently from the trusted
workflow run or release tag. Do not trust the downloaded manifest as the source
of expected policy values. In the downloaded directory:

```sh
REPOSITORY=deploywhisper/deploywhisper
SOURCE_REF=refs/heads/develop # for a release use refs/tags/vVERSION
SOURCE_SHA=EXPECTED_FULL_COMMIT_SHA
sha256sum --check SHA256SUMS
for subject in ./*.tar.gz SHA256SUMS source-manifest.json; do
  gh attestation verify "$subject" \
    --bundle artifact.intoto.jsonl --repo "$REPOSITORY" \
    --signer-workflow "$REPOSITORY/.github/workflows/release-artifacts.yml" \
    --source-ref "$SOURCE_REF" --source-digest "$SOURCE_SHA" \
    --deny-self-hosted-runners
done
```

Use a GitHub CLI version supporting these identity/source flags. Verification
checks the actual subject's hash, signed repository/workflow/source identity,
SLSA predicate and hosted runner policy. Checksums alone cannot authenticate a
publisher. Retain the native bundle alongside every archive; an asset filename
ending in `.intoto.jsonl` alone proves nothing.

For negative verification, copy the archive, append a byte, and run the same
command against the altered file; it must fail. Repeat against the intact
archive with a different repository, signer workflow, source ref and source
digest individually; each must fail. These checks need a real hosted signed
bundle. Offline unit tests prove deterministic packaging and version/source
guards, not signature verification.

## Published v1.4.0 consumer policy

The verified stable release source is `935f3bbc88907948de8ae25bd2a361d04044ebc6`, ref `refs/tags/v1.4.0`. Download the four uploaded assets from [v1.4.0](https://github.com/deploywhisper/deploywhisper/releases/tag/v1.4.0); automatic GitHub source ZIP/tar links are separate unsigned distributions. Add `--signer-digest "$SOURCE_SHA"` to the verification loop above. The archive, checksum file and manifest all passed this strict policy and five independent negative cases.

The verified image index is `ghcr.io/deploywhisper/deploywhisper@sha256:07fff3cafcb05829ae82303553d3584cccc0cf91a92877ebb798568ce1989c84`. Verify it with `gh attestation verify oci://IMAGE@DIGEST --bundle-from-oci --repo deploywhisper/deploywhisper --signer-workflow deploywhisper/deploywhisper/.github/workflows/release.yml --signer-digest "$SOURCE_SHA" --source-digest "$SOURCE_SHA" --source-ref refs/tags/v1.4.0 --deny-self-hosted-runners`, substituting the image/digest and trusted SHA above. Pin this digest for deployment instead of relying only on a floating alias. [Publication evidence](../verification/v1.4.0-release.json) includes checks for both image platforms and all promoted aliases.
