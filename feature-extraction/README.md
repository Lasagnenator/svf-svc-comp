# SVC Extraction Demo
To run this locally outside of SVC
## Prerequisite

- OS: MacOS or Ubuntu >=22.04
- Python: 3.8 - 3.11

### Install PySvf and other dependencies
```
python3 -m pip install -i https://test.pypi.org/simple/ -U pysvf
python3 -m pip install pyyaml
```

### clone this project

```
git clone https://github.com/bjjwwang/SVC-Extraction
cd SVC-Extraction
```

### Try demo

```
python3 extract.py multivar_1-1.ll
```

Note: The initial commit of this component of SVC was primarily written by bjjwwang and ConstantlyRecompiling.

## TODO
- Support Line and Column display.
