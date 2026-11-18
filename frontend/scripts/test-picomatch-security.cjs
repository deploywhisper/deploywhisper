'use strict';

// npm audit matches published package identities, so it cannot certify our
// local fork. Verify the actual installed bytes and behavior independently.
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const frontend = path.resolve(__dirname, '..');
const vendor = path.join(frontend, 'vendor');
const provenance = JSON.parse(fs.readFileSync(path.join(vendor, 'picomatch-provenance.json'), 'utf8'));
const installed = path.dirname(require.resolve('picomatch/package.json', { paths: [frontend] }));
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');

function match(pattern, input, options = {}) {
  const source = `const p = require(${JSON.stringify(installed)}); process.stdout.write(JSON.stringify(p.isMatch(${JSON.stringify(input)}, ${JSON.stringify(pattern)}, ${JSON.stringify(options)})));`;
  const result = spawnSync(process.execPath, ['-e', source], {
    encoding: 'utf8',
    timeout: 2500,
    maxBuffer: 1024 * 1024,
    killSignal: 'SIGKILL',
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test('installed picomatch is the provenance-checked local security fork', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(installed, 'package.json'), 'utf8'));
  assert.equal(pkg.name, '@deploywhisper/picomatch');
  assert.equal(pkg.version, '4.0.7');
  assert.equal(pkg.private, true);
  assert.equal(pkg.deploywhisperPatch.advisory, 'GHSA-fc5q-39xc-vjpf');
  assert.equal(provenance.upstream.version, '4.0.7');
  assert.equal(provenance.advisory, 'GHSA-fc5q-39xc-vjpf');
  const archive = fs.readFileSync(path.join(vendor, provenance.archive));
  const integrity = 'sha512-' + crypto.createHash('sha512').update(archive).digest('base64');
  assert.equal(integrity, provenance.archiveIntegrity);
  assert.equal(sha256(fs.readFileSync(path.join(vendor, 'picomatch-4.0.7-security.patch'))), provenance.patchSha256);
  for (const [filename, expected] of Object.entries(provenance.filesSha256)) {
    assert.equal(sha256(fs.readFileSync(path.join(installed, filename))), expected, filename);
  }
  const lock = JSON.parse(fs.readFileSync(path.join(frontend, 'package-lock.json'), 'utf8'));
  const nodes = Object.entries(lock.packages).filter(([name]) => /(?:^|\/)node_modules\/picomatch$/.test(name));
  assert.ok(nodes.length > 0);
  for (const [name, node] of nodes) {
    assert.equal(node.name, '@deploywhisper/picomatch', name);
    assert.equal(node.integrity, integrity, name);
    assert.equal(node.link, undefined, name);
    assert.ok(node.resolved.endsWith(provenance.archive), name);
  }
});

const hostile = [
  ['+(*a)', 'a'.repeat(40) + '!'],
  ['+(*)b', 'a'.repeat(40) + 'c'],
  ['*(*a)', 'a'.repeat(40) + '!'],
  ['+(a*b)', 'ab'.repeat(30) + '!'],
  ['pre+(*a)post', 'pre' + 'a'.repeat(40) + '!post'],
  ['+([ab]*a)', 'a'.repeat(40) + '!'],
  ['+(*?(a))b', 'a'.repeat(40) + 'c'],
  ['+(*a|b)', 'a'.repeat(40) + '!'],
  ['+(ab|abab)', 'ab'.repeat(30) + '!'],
  ['*(ab|abab)', 'ab'.repeat(30) + '!'],
  [String.raw`+(\w|a\w)`, 'a'.repeat(40) + '!'],
  [String.raw`+(\d|1\d)`, '1'.repeat(40) + '!'],
  [String.raw`+(a|\x61a)`, 'a'.repeat(40) + '!'],
  [String.raw`+(a|\u0061a)`, 'a'.repeat(40) + '!'],
  ['+("a"|"aa")', 'a'.repeat(40) + '!'],
  ['+("a"|aa)', 'a'.repeat(40) + '!'],
  ['+(a|"aa")', 'a'.repeat(40) + '!'],
  ["+('a'|'aa')", 'a'.repeat(40) + '!'],
];
for (const [pattern, input] of hostile) {
  test(`repeated extglob remains bounded: ${pattern}`, () => {
    for (const options of [{}, { maxExtglobRecursion: false }, { maxExtglobRecursion: 100 }]) {
      assert.equal(match(pattern, input, options), false);
    }
  });
}

test('case-insensitive and Unicode repeat ambiguity remains bounded', () => {
  for (const options of [{ nocase: true }, { flags: 'i' }, { flags: 'iu' }, { nocase: true, maxExtglobRecursion: false }]) {
    assert.equal(match('+(a|AA)', 'a'.repeat(40) + '!', options), false);
    assert.equal(match('+(σ|ςς)', 'σ'.repeat(40) + '!', options), false);
  }
});

test('ordinary glob matching and test discovery remain compatible', () => {
  const examples = [
    ['**/*.{js,ts}', 'src/main.ts', true],
    ['**/*.{js,ts}', 'src/main.css', false],
    ['**/?(*.)+(test|spec).[jt]s?(x)', 'src/button.test.tsx', true],
    ['**/?(*.)+(test|spec).[jt]s?(x)', 'src/button.tsx', false],
    ['+(test|spec)', 'testspec', true],
    ['+(foo|bar)', 'foobarfoo', true],
    ['+(*(a)|*(b))', 'abba', true],
    ['foo/!(bar).js', 'foo/baz.js', true],
    ['[ab].js', 'a.js', true],
  ];
  for (const [pattern, input, expected] of examples) {
    assert.equal(match(pattern, input), expected, `${pattern}: ${input}`);
  }
});

test('upstream advisory tracking rejects unknown or changed security findings', () => {
  const { validateAdvisories } = require('./check-picomatch-advisories.cjs');
  const known = {
    id: 1247710,
    url: 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf',
    title: 'picomatch vulnerable to ReDoS through single-branch repeated extglobs',
    severity: 'high',
    vulnerable_versions: '<=4.0.7',
  };
  assert.deepEqual(validateAdvisories({ picomatch: [known] }), [1247710]);
  assert.deepEqual(validateAdvisories({}), []);
  for (const invalid of [null, [], { other: [] }, { picomatch: null },
    { picomatch: [{ ...known, id: 9999999 }] },
    { picomatch: [known, { ...known, url: 'https://github.com/advisories/GHSA-new-advisory' }] },
    { picomatch: [{ ...known, severity: 'critical' }] },
    { picomatch: [{ ...known, vulnerable_versions: '<=4.0.8' }] }]) {
    assert.throws(() => validateAdvisories(invalid));
  }
});
