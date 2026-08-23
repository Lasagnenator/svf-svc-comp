
## Local setup

Install the pinned Python dependencies into a virtual environment:

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

## Dockerfile usage
Attached is a dockerfile that when built into an image, provides an environment in which SVF can be built and run for the competition.

Instructions for using the dockerfile (assuming that this repository has been cloned to a local machine with macOS/WSL), starting with the current directory as svf-svc-comp:
```sh
docker build -t svf-comp:01 .
docker run -itd svf-comp:01
```

Now, it should be possible to access and work within the container environment using VSCode similar to how it could be done for COMP6131. (Pulling from the repo is easy, but pushing changes to the repo requires setting up the container to allow for SSHing (will set up later, soz)).

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

Use the already-present SV-COMP corpus; the runner never clones or downloads it. Activate the
repository venv first so both the runner and `svf_run.py` use the preinstalled dependencies:

```sh
python tests/tester.py "$(realpath ../sv-benchmarks-main-c)" "$PWD" \
  --reach --sample 1% --seed 0
```

Sampling is deterministic and stratified by property, data model, and expected verdict. Omit
`--sample` for the complete selected population, use `--specific array-crafted/bAnd1` for one
benchmark family, or add `--dry-run` to inspect `manifest.json` without executing the tool.

The default `quick` profile uses 30 CPU seconds, 45 wall seconds, and 5 GiB. Use `--profile
competition` for 960 CPU seconds, 1020 wall seconds, and 15 GiB, or override individual limits.
Wall time applies to the process group; CPU and memory use POSIX per-process limits, so this is an
approximation of BenchExec's aggregate accounting. Results are written under `test-results/<timestamp>/`:

- `manifest.json` records the corpus, limits, sample seed, and exact selected runs.
- `results.jsonl` is flushed after every run and includes verdict, score, termination reason,
  diagnostic tail, log path, and the direct tool invocation.
- `logs/` retains complete stdout and stderr for debugging.
- `summary.json` reports the provisional raw score and result counts; `--output FILE.csv` adds CSV.

Scoring uses the SV-COMP raw weights: correct true `+2`, correct false `+1`, false alarm `-16`,
and missed violation `-32`. Unknowns, timeouts, crashes, and unsupported tasks score zero. This is
a progress score, not an official competition score, because the local runner does not validate
witnesses.

The unchanged competition entrypoint currently ignores `--bits`, so ILP32 tasks are recorded as
unsupported rather than scored under the wrong data model. Memory-safety and cleanup tasks are
also recorded as unsupported because `svf_run.py` does not implement those property dispatches.
Overflow tasks are not score-eligible yet because that branch currently detects buffer bounds,
whereas SV-COMP's `no-overflow.prp` asks about signed-integer overflow.
