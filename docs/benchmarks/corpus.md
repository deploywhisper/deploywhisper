# Benchmark Corpus

DeployWhisper's public benchmark corpus lives in `benchmarks/corpus/v1`.

Each scenario is synthetic and must include:

- input artifacts
- expected findings
- expected evidence
- expected verdict rationale
- labels
- licensing metadata
- safety metadata confirming that the sample is public and contains no secrets, customer data, or non-public information

Expected evidence selectors must be literal text found in the referenced artifact so benchmark evidence remains directly inspectable.

Run validation with:

```sh
python cli.py benchmark validate-corpus
```

The validator rejects missing required fields, missing artifact files, unknown evidence references, missing evidence selectors, unsafe artifact content, non-public license metadata, and samples marked as containing secrets, customer data, or non-public information.

Run the corpus against the product analysis core with:

```sh
python cli.py benchmark run
```

Use `--path` to run a different local corpus root:

```sh
python cli.py benchmark run --path benchmarks/corpus/v1
```

The command exits with `0` only when every scenario meets its benchmark expectation. A nonzero exit still emits structured JSON so CI and maintainers can inspect scenario-level failures or corpus validation errors without scraping tracebacks.

Benchmark execution is local-first: the runner reads corpus artifacts from disk and routes them through DeployWhisper's local analysis services. The benchmark verdict is advisory evidence for maintainers; it does not approve, block, deploy, or mutate infrastructure.

The runner validates and loads the corpus, replays each scenario through the same parser, evidence extraction, scoring, finding, and Evidence Law path used by product analysis, and emits JSON with:

- aggregate pass/fail counts and total latency
- per-scenario status, pass/fail, latency, unsupported reasons, partial-coverage warnings, actual recommendation, severity, and benchmark verdict
- observed findings with confidence and evidence references
- finding coverage and selector-level evidence coverage against the scenario expectations
- Evidence Law status, detail, and violation records
