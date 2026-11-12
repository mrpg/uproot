# Model case snapshots

Generated from [uproot-proofs](https://github.com/mrpg/uproot-proofs) commit
`0a9fc8d126ed6fbdcf0c53112905899bd61e55cc` (0BSD).
These cases are deterministic; regenerate them when the model or generators change.
The snapshots contain 56,160 room admission cases and 81,760 page requests,
stored as gzip files to keep the repository small (about 1.3 MB combined).

Run `./test-models.sh` to run the randomized room checks once and replay both
snapshots with one shard per available CPU (`nproc`). Each replay worker has
an isolated in-memory database; coverage is disabled to avoid concurrent writes.
Worker failures print their logs and fail the script. `release.sh` runs this
script too. Running the tests does not require Lean.

To regenerate, install Lean and use a sibling `uproot-proofs` checkout. From
the uproot repository root, run with Bash:

```bash
set -o pipefail
timeout 300s uv run --project "$PWD" --directory ../uproot-proofs \
    lake exe room-cases | gzip -n -9 > tests/cases/room-cases.jsonl.gz
timeout 300s uv run --project "$PWD" --directory ../uproot-proofs \
    lake exe page-cases | gzip -n -9 > tests/cases/page-cases.jsonl.gz
```

Update the source commit above after regenerating. `gzip -n` omits timestamps
and filenames so identical generator output produces identical snapshots.
