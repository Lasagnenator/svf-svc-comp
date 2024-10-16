# svf-svc-comp

Run `setup.sh` once to download the SVF binaries. `svf-svc-comp` uses [this](https://github.com/SVF-tools/SVF/releases/tag/SVF-3.0) specific release of SVF.

## Requirements

* `svf_run.py` does not use any libraries besides the standard Python ones.
* `include_replace.c` needs to be in the same directory as `svf_run.py`.
* After setup, the directory `svf` must be next to `svf_run.py`.

## Running

The main script is `svf_run.py`.

```
usage: python3 svf_run.py [-h] [--version] [--bits {32,64}] [--prop PROP] c_file

positional arguments:
  c_file          input C file

options:
  -h, --help      show this help message and exit
  --version       show program's version number and exit
  --bits {32,64}  bit width
  --prop PROP     property files
```

Notes:
* `c_file` should be a C file that is valid for SV-Comp.
* `--bits` option defaults to `64` if none is specified.
* `--prop` option can be used multiple times for every property file.
