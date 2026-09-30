#!/usr/bin/env python3
"""
Synchronize persisted collection snapshots from the data-collection branch
into the current working tree without switching branches.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "data-collection"

SYNC_PATHS = (
    "data/interim/ojp_snapshots/",
    "data/interim/weather_snapshots/",
)

MANIFEST_PATH = "data/collection_manifest.csv"


def run_git(
    repo_root: Path,
    args: list[str],
    *,
    text: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=text,
    )


def ensure_git_repo(repo_root: Path) -> None:
    result = run_git(
        repo_root,
        ["rev-parse", "--is-inside-work-tree"],
    )
    if result.stdout.strip() != "true":
        raise RuntimeError(f"Not a Git repository: {repo_root}")


def fetch_data_branch(
    repo_root: Path,
    remote: str,
    branch: str,
) -> str:
    remote_ref = f"refs/remotes/{remote}/{branch}"

    run_git(
        repo_root,
        [
            "fetch",
            remote,
            f"{branch}:{remote_ref}",
        ],
    )

    return f"{remote}/{branch}"


def list_ref_files(
    repo_root: Path,
    ref: str,
) -> list[str]:
    result = run_git(
        repo_root,
        ["ls-tree", "-r", "--name-only", ref],
    )
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def is_collection_file(path: str) -> bool:
    return (
        any(path.startswith(prefix) for prefix in SYNC_PATHS)
        and path.endswith(".csv")
    ) or path == MANIFEST_PATH


def read_ref_file(
    repo_root: Path,
    ref: str,
    path: str,
) -> bytes:
    result = run_git(
        repo_root,
        ["show", f"{ref}:{path}"],
        text=False,
    )
    return result.stdout


def sync_from_ref(
    repo_root: Path,
    ref: str,
) -> dict[str, int]:
    all_files = list_ref_files(repo_root, ref)
    selected = sorted(
        path
        for path in all_files
        if is_collection_file(path)
    )

    ojp_count = 0
    weather_count = 0
    manifest_count = 0

    for relative_path in selected:
        target = repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            read_ref_file(repo_root, ref, relative_path)
        )

        if relative_path.startswith(SYNC_PATHS[0]):
            ojp_count += 1
        elif relative_path.startswith(SYNC_PATHS[1]):
            weather_count += 1
        elif relative_path == MANIFEST_PATH:
            manifest_count += 1

    if ojp_count == 0:
        raise RuntimeError(
            f"No OJP snapshots found in {ref}."
        )
    if weather_count == 0:
        raise RuntimeError(
            f"No weather snapshots found in {ref}."
        )

    return {
        "ojp_snapshots": ojp_count,
        "weather_snapshots": weather_count,
        "manifest_files": manifest_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
    )
    parser.add_argument(
        "--ref",
        default=None,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()

    ensure_git_repo(repo_root)

    if args.ref:
        ref = args.ref
    elif args.no_fetch:
        ref = args.branch
    else:
        ref = fetch_data_branch(
            repo_root=repo_root,
            remote=args.remote,
            branch=args.branch,
        )

    counts = sync_from_ref(repo_root, ref)

    print("=" * 68)
    print("COLLECTION DATA SYNC")
    print("=" * 68)
    print(f"Source ref: {ref}")
    print(f"OJP snapshots: {counts['ojp_snapshots']}")
    print(
        f"Weather snapshots: "
        f"{counts['weather_snapshots']}"
    )
    print(
        f"Manifest copied: "
        f"{bool(counts['manifest_files'])}"
    )
    print("Local analysis data are ready.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
