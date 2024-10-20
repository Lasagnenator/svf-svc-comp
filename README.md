# svf-svc-comp

Run `setup.sh` once to download the SVF binaries. `svf-svc-comp` uses [this](https://github.com/SVF-tools/SVF/releases/tag/SVF-3.0) specific release of SVF.

## Requirements

* `svf_run.py` does not use any libraries besides the standard Python ones.
* `include_replace.c` needs to be in the same directory as `svf_run.py`.
* After setup, the directory `svf` must be next to `svf_run.py`.
* This project relies on `clang` being available to use.

## Running

The main script is `svf_run.py`.

```
usage: svf_run.py [-h] [--version] [--bits {32,64}] [--prop PROP]
                  [--verbose] [--debug]
                  c_file

positional arguments:
  c_file            input C file

options:
  -h, --help        show this help message and exit
  --version         show program's version number and exit
  --bits {32,64}    bit width
  --prop PROP       property file
  --verbose, -v     verbose output
  --debug, -d       debug output
  --time-limit int  SVF time limit
```

Notes:
* `c_file` should be a C file that is valid for SV-Comp.
* `--bits` defaults to `64` if none is specified.
* `--prop` points to a file containing the desired property to be checked.
* `--verbose` prints a lot of information about the internal graph.
