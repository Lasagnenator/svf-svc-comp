
## Local setup

Ensure you have `clang` and `python` installed. SVF-SVC expects `clang-21` and `python-3.12`. Other versions may work but are unsupported. To run tests, you will need to also install `pyyaml`.

Install the dependencies into a virtual environment:

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

You can build a self-contained competition archive using the build script. The output is `dist/svf-svc.zip` and is suitable to upload.
```sh
./build.sh
```

## Dockerfile usage
Attached is a dockerfile that when built into an image, provides an environment in which SVF can be built and run for the competition.

Dockerfile now has SSH. For using the Dockerfile with SSH, (assuming local machine operates on macOS/WSL), start with current directory as svf-svc-comp and refer to instructions below:

Generate your own SSH key:
```sh
ssh-keygen -t ed25519 -C "your.email@example.com"
```

Then copy your public key to authorized_keys. This file is gitignored:
```sh
cat ~/.ssh/id_ed25519.pub > authorized_keys
```

Build the docker image and run the container as so:
```sh
docker build -t svf-comp:01 .
docker run -itd -p 2222:22 --name svf-comp -v $(pwd):/home/svf/svf-svc-comp svf-comp:01
```
Then connect via SSH:
```sh
ssh svf@localhost -p 2222
```

If you rebuild and reconnect to the same host/port, you may see a "host key
has changed" warning. This is expected. Clear it with:
```sh
ssh-keygen -R "[localhost]:2222"
```

The current entrypoint is `svf_run.py`. From the repository root, run:
```sh
python3 svf_run.py --prop prop_file_path c_source_file_path
```

To explain what happens in the codebase, similar to what we did in assignment 3:
* Preprocess the source C file
* Compile it to LLVMIR
* Feed the LLVMIR into the assignment 3 program
* Traverse through the ICFG using abstract execution
* If there's a bug/error in the C source code, then track it somehow (currently it just adds the reason and ICFGNode to a list)

For the file `AbstractInterpreation.py`, theres some comments with the text `###SVF SV-COMP-ADDITION` to show where some changes have been made compared to what would be used for COMP6131 assignment 3.


A running list of things to work on:
* TODO: There's scripts for witness gen (yaml and graphml), now have to make our run of SVF output info to provide to those scripts, to generate the witnesses
* TODO: Implement the actual checking for conditions/categories like reachability, overflow, memory errors, etc (and then provide those to witness gen)
          (reachability is now done)   
* TODO: Implement testing using CPAChecker to accept a witness and certify whether it is accurate

## Local benchmark scoring

The runner reproduces SV-COMP 2026 scoring for the three C meta categories svf-svc competes in:
`reachsafety`, `memsafety`, and `softwaresystems`. Leaf categories mirror `benchmark-defs/svf-svc.xml`.

### Fetching benchmarks

The corpus is large, so it is fetched on demand and never committed. `tests/fetch_benchmarks.py`
performs a blobless sparse checkout and materialises only what is needed. The default destination
is `../sv-benchmarks`, outside the repository.

```sh
# Task definitions and property files only (no C sources).
python tests/fetch_benchmarks.py --category reachsafety --metadata-only

# Or every family used by a category.
python tests/fetch_benchmarks.py --category reachsafety
```

For a sampled run, fetch metadata first, select the sample, then materialise only those sources:

```sh
python tests/tester.py ../sv-benchmarks "$PWD" \
  --category reachsafety --sample-count 50 --seed 0 --dry-run --results-dir /tmp/sample
python tests/fetch_benchmarks.py --from-manifest /tmp/sample/manifest.json --dest ../sv-benchmarks
```

### Running

Activate the SVF-Python environment so the runner and `svf_run.py` share bindings, then run the
same seed without `--dry-run` to execute the identical selection:

```sh
python tests/tester.py ../sv-benchmarks "$PWD" \
  --category reachsafety --sample-count 50 --seed 0
```

Repeat `--category` to combine meta categories. Sampling is deterministic and stratified by leaf
category, data model, and expected verdict, and every leaf category is represented when the sample
is large enough. Use `--sample 1%` for a proportional sample, omit both for the full population, or
add `--dry-run` to inspect `manifest.json` without executing the tool.

The default `quick` profile uses 30 CPU seconds, 45 wall seconds, and 5 GiB. Use `--profile
competition` for the SV-COMP limits of 900 CPU seconds, 900 wall seconds, and 15 GB, or override
individual limits. Wall time applies to the process group; CPU and memory use POSIX per-process
limits, so this approximates rather than replaces BenchExec's aggregate accounting.

Results are written under `test-results/<timestamp>/`:

- `manifest.json` records the corpus, categories, limits, sample seed, and exact selected runs.
- `results.jsonl` is flushed after every run and includes verdict, score, witness status,
  termination reason, diagnostic tail, log path, and the direct tool invocation.
- `logs/` retains complete stdout, stderr, and generated witnesses.
- `summary.json` reports the score, normalized leaf-category scores, and result counts;
  `--output FILE.csv` adds CSV.

### Scoring and witness validation

Scoring uses the SV-COMP weights: correct true `+2`, correct false `+1`, false alarm `-16`, and
missed violation `-32`. Unknowns, timeouts, crashes, and unsupported tasks score zero.

Witnesses are retained under `logs/`. Validation is reported per run in the `witness_validation`
field but does not change the score, so a run needs no validator. Note that SV-COMP itself awards no
positive points for a correct answer whose required witness is not confirmed, so the score here is
an upper bound on what the competition would award.

To confirm witnesses, supply an external validator. `tests/validate_witness.sh` wraps CPAchecker and
exits zero only on confirmation. It has been verified against CPAchecker 4.2, which needs Java 17 or
newer and selects validation through config files rather than a command-line flag:

```sh
export CPACHECKER_HOME=/opt/CPAchecker-4.2-unix
python tests/tester.py ../sv-benchmarks "$PWD" \
  --category reachsafety --profile competition \
  --validation-wall-limit 600 \
  --validator-command 'tests/validate_witness.sh {witness} {input} {property} {bits}'
```

Placeholders are `{witness}`, `{input}`, `{property}`, and `{bits}`. Previously computed results can
be supplied instead with `--validation-results results.json`, a JSON object mapping run IDs to
`correct` or `unconfirmed`.

Validators reject a witness outright when its declared architecture differs from the task's data
model, so `svf_run.py` passes `--bits` to clang and records the same value in the witness. Most
ReachSafety tasks are ILP32, so without this no ILP32 witness can be validated.

### Current capability

Benchmark selection covers all three meta categories. Memory-safety, cleanup, termination, and
signed-integer overflow tasks are selected and reported, then marked unsupported and scored zero
rather than being silently dropped. Memory dispatch is commented out in `SUPPORTED_PROPERTIES` and
can be re-enabled once `svf_run.py` implements it. The existing overflow path detects buffer bounds, whereas `no-overflow.prp` concerns signed-integer overflow.

### Continuous integration

`.github/workflows/benchmark.yml` runs on pull requests into `main`. It executes the tester unit
tests, caches the benchmark metadata checkout, selects a deterministic sample seeded by the commit
SHA, fetches only those sources, runs them, and uploads the results directory as an artifact.

The tester exits non-zero when the harness itself fails, meaning the tool never started or the run
was interrupted, so CI gates on its exit code. Analyser unknowns and tool errors are reported
without failing the build, since they reflect coverage rather than runner health. Use the workflow
dispatch inputs to choose a category or sample size, capped at 100 runs.
