# svf-svc

Run `setup.sh` once to download the SVF binaries. `svf-svc` uses [this](https://github.com/SVF-tools/SVF/releases/tag/SVF-3.0) specific release of SVF.

## Requirements

* `svf_run.py` does not use any libraries besides the standard Python ones.
* `include_replace.c` needs to be in the same directory as `svf_run.py`.
* After setup, the directory `svf` must be next to `svf_run.py`.
* This project relies on `clang` being available to use.

## Running

The main script is `svf_run.py`.

```
usage: svf_run.py [-h] [--version] [--bits {32,64}] [--prop PROP]
                  [--verbose] [--time-limit TIME_LIMIT] [--witness WITNESS]
                  c_file

positional arguments:
  c_file                input C file in SV-Comp format

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --bits {32,64}        bit width
  --prop PROP           property file
  --verbose, -v         display internals
  --time-limit int      SVF time limit
  --witness file        witness output
```

Notes:
* `c_file` should be a C file that is valid for SV-Comp.
* `--bits` defaults to `64` if none is specified.
* `--prop` points to a file containing the desired property to be checked.
* `--verbose` prints a lot of information about the internals.
* `--witness` must be a writeable file path.

## Dockerfile usage
Attached is a dockerfile that when built into an image, provides an environment in which SVF can be built and run for the competition.

Instructions for using the dockerfile (assuming that this repository has been cloned to a local machine with macOS/WSL), starting with the current directory as svf-svc-comp:
``` $ docker build -t svf-comp:01 .
 $ docker run -itd svf-comp:01
```

Now, it should be possible to access and work within the container environment using VSCode similar to how it could be done for COMP6131. (Pulling from the repo is easy, but pushing changes to the repo requires setting up the container to allow for SSHing (will set up later, soz)).

One thing to mention is that you should run the command `git checkout setup-tooling` to enter this branch to access these changes, since it's currently not on main/master (replace setup-tooling with the branch you're trying to test/work in if needed).

Right now, there exists a script `python_svf.py`, and from the terminal in the container in VSCode, you can run:
``` $ python3 python_svf.py c_source_file_path
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
* TODO: Implement testing using CPAChecker to accept a witness and certify whether it is accurate