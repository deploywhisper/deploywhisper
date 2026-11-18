# Local picomatch security fork

`deploywhisper-picomatch-4.0.7-security.3.tgz` replaces the existing transitive `picomatch`
package with **`@deploywhisper/picomatch@4.0.7`**. It is a local fork, not a
published upstream security release. The upstream MIT license is retained both
inside the archive and in `picomatch-LICENSE`.

Upstream `picomatch@4.0.7` is affected by
[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf).
As checked on 2026-11-18, no patched registry release exists. The fork retains
ordinary matching and uses the parser's existing literalization fallback for
unsafe repeated extglob bodies. Literal alternatives must use plain ASCII letters/digits/underscore/dot/slash/dash/space and be prefix-free after ASCII case-folding;
wildcard, escaped, quoted, non-ASCII, bracket and nested nonliteral bodies are conservatively literalized.
Existing safe flat character-star rewrites remain available. The safety checks
also apply when `maxExtglobRecursion` is false. This deliberately narrows unsafe
pattern behavior; it does not claim that arbitrary raw regular expressions are
safe for untrusted use.

## Provenance and reproduction

`picomatch-provenance.json` records the exact upstream registry archive integrity,
local archive integrity, readable patch digest and every installed file's SHA256.
The upstream source is `https://registry.npmjs.org/picomatch/-/picomatch-4.0.7.tgz`.
Unpack that archive, apply `picomatch-4.0.7-security.patch` using `patch -p1`, then
run `npm pack --ignore-scripts` in the patched directory. The committed archive
was generated with npm11.12.1. Its scope/name and private flag prevent confusing
it with an upstream release or accidentally publishing it.

The fork has a distinct identity, so npm audit cannot inherit the upstream
advisory or certify this local patch. Both normal audit gates remain enabled.
`npm test` independently verifies actual installed bytes, lock/archive integrity,
license provenance and bounded exploit matching in child processes. A security
regression or archive mismatch must fail CI even when npm audit reports zero.
No advisory allowlist or audit-level reduction is used.

Remove this override and archive only when a maintained upstream release fixes
the advisory and passes the same exploit/compatibility corpus. Re-run the full
frontend typecheck, tests, build and Docker build after any fork change. Do not
update the expected hashes without reviewing the source patch and regressions.

The existing transitive library is also anchored as a direct development dependency
so the `$picomatch` override resolves its local archive from the frontend root
rather than each transitive dependency directory. This adds no independent
library or runtime dependency.

`npm run audit:picomatch-upstream` queries the fixed npm bulk advisory endpoint
for the original picomatch4.0.7 identity with a total deadline and response-size
bound. It recognizes only the recorded GHSA-fc5q-39xc-vjpf metadata, then requires
the local provenance/exploit suite to pass. New or changed advisories and registry
failures fail closed. This preserves future upstream advisory tracking despite
the explicit fork identity. Offline tests exercise unknown-advisory rejection.
