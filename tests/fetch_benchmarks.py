#!/usr/bin/env python3
"""Fetch only the SV-COMP task families used by the categories svf-svc competes in.

The corpus is large, so this performs a blobless sparse checkout and materialises
just the directories referenced by the selected meta categories. The default
destination is outside the repository so benchmarks are never committed.

    python tests/fetch_benchmarks.py --category reachsafety
    python tests/fetch_benchmarks.py --all --dest /srv/sv-benchmarks
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tester import SVCOMP26_CATEGORIES  # noqa: E402


REPOSITORY = "https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks.git"
REVISION = "svcomp26"
METADATA_PATTERNS = ("/c/*.set", "/c/**/*.yml", "/c/properties/*")


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def clone(dest, revision):
    run(["git", "clone", "--filter=blob:none", "--sparse",
         "--branch", revision, "--depth", "1", REPOSITORY, str(dest)])


def set_sparse_patterns(dest, patterns):
    run(["git", "-C", str(dest), "sparse-checkout", "set", "--no-cone", *patterns])


def selected_set_names(categories):
    names = set()
    for category in categories:
        for spec in SVCOMP26_CATEGORIES[category]:
            names.update(spec.includes)
            names.update(spec.excludes)
    return sorted(names)


def source_directories(dest, set_names):
    """Read the category .set files and collect the directories they reference."""
    directories = set()
    missing = []
    for name in set_names:
        set_path = dest / "c" / f"{name}.set"
        if not set_path.is_file():
            missing.append(name)
            continue
        for line in set_path.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            parent = Path(entry).parent
            directories.add("/c" if parent in (Path("."), Path("")) else f"/c/{parent.as_posix()}")
    return sorted(directories), missing


def manifest_source_patterns(manifest_path):
    """Resolve the exact input files referenced by a tester manifest."""
    manifest = json.loads(Path(manifest_path).read_text())
    patterns = set()
    for task in manifest.get("selected", []):
        task_dir = Path(task["yaml_relative"]).parent
        for source in task["input_files"]:
            patterns.add(f"/{(task_dir / source).as_posix()}")
    return sorted(patterns)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", action="append", choices=tuple(SVCOMP26_CATEGORIES),
                        help="meta category to fetch; repeat to combine")
    parser.add_argument("--all", action="store_true", help="fetch every competed-in category")
    parser.add_argument("--dest", type=Path, default=Path("../sv-benchmarks"),
                        help="checkout destination (default: ../sv-benchmarks)")
    parser.add_argument("--revision", default=REVISION,
                        help=f"benchmark tag or branch (default: {REVISION})")
    parser.add_argument("--metadata-only", action="store_true",
                        help="fetch task definitions and property files but no C sources")
    parser.add_argument("--from-manifest", type=Path,
                        help="fetch only the sources listed in a tester manifest.json")
    parser.add_argument("--force", action="store_true", help="replace an existing destination")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    dest = args.dest.resolve()

    # Incremental mode: add the sampled sources to an existing metadata checkout.
    if args.from_manifest:
        if not (dest / ".git").is_dir():
            build_parser().error(f"no existing checkout to extend: {dest}")
        patterns = manifest_source_patterns(args.from_manifest)
        if not patterns:
            build_parser().error(f"manifest lists no input files: {args.from_manifest}")
        print(f"Materialising {len(patterns)} sampled source files in {dest}")
        try:
            set_sparse_patterns(dest, [*METADATA_PATTERNS, *patterns])
        except subprocess.CalledProcessError as error:
            print(f"git failed with exit code {error.returncode}", file=sys.stderr)
            return error.returncode
        print(f"Corpus ready: {dest}")
        return 0

    categories = sorted(SVCOMP26_CATEGORIES) if args.all else (args.category or [])
    if not categories:
        build_parser().error("select --category, --all, or --from-manifest")

    if dest.exists():
        if not args.force:
            build_parser().error(f"destination already exists (use --force to replace): {dest}")
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"Cloning {REPOSITORY} at {args.revision} into {dest}")
    try:
        clone(dest, args.revision)
        set_sparse_patterns(dest, METADATA_PATTERNS)
        if args.metadata_only:
            print("Metadata-only checkout complete; C sources were not fetched.")
            return 0

        set_names = selected_set_names(categories)
        directories, missing = source_directories(dest, set_names)
        if missing:
            print(f"Warning: {len(missing)} set files not found: {', '.join(missing)}",
                  file=sys.stderr)
        if not directories:
            print("No source directories resolved from the selected categories.", file=sys.stderr)
            return 1
        print(f"Materialising {len(directories)} task directories for: {', '.join(categories)}")
        set_sparse_patterns(dest, [*METADATA_PATTERNS, *directories])
    except subprocess.CalledProcessError as error:
        print(f"git failed with exit code {error.returncode}", file=sys.stderr)
        return error.returncode

    print(f"Corpus ready: {dest}")
    print(f"Run: python tests/tester.py {dest} \"$PWD\" --category {categories[0]} --sample-count 50")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
