'use strict';

// npm audit scans the explicit local fork identity. Keep tracking its upstream
// source separately, and accept its one known advisory only with patch proof.
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const ENDPOINT = 'https://registry.npmjs.org/-/npm/v1/security/advisories/bulk';
const MAX_BYTES = 64 * 1024;
const KNOWN = Object.freeze({
  id: 1247710,
  url: 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf',
  title: 'picomatch vulnerable to ReDoS through single-branch repeated extglobs',
  severity: 'high',
  vulnerable_versions: '<=4.0.7',
});

function validateAdvisories(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)
      || Object.keys(payload).some(key => key !== 'picomatch')) {
    throw new Error('unrecognized upstream advisory response');
  }
  if (!Object.hasOwn(payload, 'picomatch')) return [];
  if (!Array.isArray(payload.picomatch)) throw new Error('invalid upstream advisory list');
  for (const advisory of payload.picomatch) {
    if (!advisory || Object.entries(KNOWN).some(([key, value]) => advisory[key] !== value)) {
      throw new Error('new or changed upstream advisory requires security review');
    }
  }
  return payload.picomatch.map(advisory => advisory.id);
}

async function fetchAdvisories() {
  const response = await fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ picomatch: ['4.0.7'] }),
    redirect: 'error',
    signal: AbortSignal.timeout(10000),
  });
  if (response.status !== 200) throw new Error('upstream registry returned unsuccessful status');
  const chunks = [];
  let size = 0;
  for await (const chunk of response.body) {
    size += chunk.length;
    if (size > MAX_BYTES) {
      await response.body.cancel().catch(() => {});
      throw new Error('upstream registry response exceeded size limit');
    }
    chunks.push(Buffer.from(chunk));
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new Error('upstream registry returned invalid JSON');
  }
}

async function main() {
  const ids = validateAdvisories(await fetchAdvisories());
  const verification = spawnSync(process.execPath, [
    '--test', path.join(__dirname, 'test-picomatch-security.cjs'),
  ], { encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024, killSignal: 'SIGKILL' });
  if (verification.error || verification.status !== 0) {
    throw new Error('local fork provenance or exploit verification failed');
  }
  console.log(`Upstream picomatch advisory tracking passed; recognized IDs: ${ids.join(',') || 'none'}. Local patch provenance and exploit regressions passed.`);
}

module.exports = { validateAdvisories };
if (require.main === module) {
  main().catch(() => {
    // Fail closed without dumping remote response bodies or environment data.
    console.error('Picomatch upstream advisory verification failed; inspect registry/advisory state and local patch verification.');
    process.exitCode = 1;
  });
}
