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
