#!/usr/bin/env python3
"""
Builds an ordered execution plan of snippet scripts to run for docs CI.

Usage:
  python ci/select-doc-pages.py --changed-file-list changed.txt --out plan.txt [--repo-root .]

Environment: (none)

Input format:
  Newline-delimited file where each line is a path (relative or absolute).
  Lines starting with '#' and empty lines are ignored.
  Only files ending with '.task.sh' are selected.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Iterable, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Select doc snippet pages to run.")
    p.add_argument(
        "--changed-file-list",
        required=True,
        type=Path,
        help="Path to a newline-delimited file of changed files.",
    )
    p.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Path to write the newline-delimited execution plan.",
    )
    p.add_argument(
        "--repo-root",
        default=".",
        type=Path,
        help="Optional repository root (for nicer logging); default='.'.",
    )
    return p.parse_args()


def normalize_path(path: Path, repo_root: Path) -> str:
    """Normalize a path to be repo-relative and use POSIX separators."""
    try:
        # Resolve to an absolute path first to make relative_to robust
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        # Path is not inside the repo_root, return its absolute path
        return path.resolve().as_posix()


@dataclass
class ExecutionPlan:
    """Represents the set of scripts to be executed."""
    scripts: List[Path] = field(default_factory=list)
    repo_root: Path = Path(".")

    @classmethod
    def from_changed_files(cls, path: Path, repo_root: Path) -> ExecutionPlan:
        """Create a plan from a file listing changed paths."""
        if not path.is_file():
            raise FileNotFoundError(f"Changed file list not found: {path}")

        lines = path.read_text(encoding="utf-8").splitlines()
        task_paths = [Path(p) for p in lines if p.strip().endswith(".task.sh")]
        unique_paths = list(dict.fromkeys(task_paths))

        return cls(scripts=unique_paths, repo_root=repo_root)

    def validate_paths_exist(self) -> None:
        """Ensure all scripts in the plan exist on disk."""
        missing = [str(p) for p in self.scripts if not p.is_file()]
        if missing:
            joined = "\n  - ".join(missing)
            raise FileNotFoundError(f"The following snippet files do not exist:\n  - {joined}")

    def expand_dependencies(self) -> None:
        """
        STUB: In the future, this will handle @depends expansion.
        For now, it's a no-op placeholder.
        """
        # TODO (v2+): Implement dependency resolution here.
        pass

    def write(self, out_path: Path) -> None:
        """Write the final, normalized plan to a file."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_paths = [normalize_path(p, self.repo_root) for p in self.scripts]
        out_path.write_text("\n".join(normalized_paths) + "\n", encoding="utf-8")

    def print_summary(self) -> None:
        """Print the plan to stderr for CI logs."""
        print("Execution plan:", file=sys.stderr)
        normalized_paths = [normalize_path(p, self.repo_root) for p in self.scripts]
        if not normalized_paths:
            print("  (empty)", file=sys.stderr)
            return
        for i, p in enumerate(normalized_paths, 1):
            print(f"  [{i:02d}] {p}", file=sys.stderr)


def main() -> int:
    args = parse_args()

    try:
        plan = ExecutionPlan.from_changed_files(
            path=args.changed_file_list, repo_root=args.repo_root
        )
    except FileNotFoundError:
        # If the changed list itself is missing, that's an error.
        raise
    except Exception:
        # If the changed list is empty or has no tasks, create an empty plan.
        plan = ExecutionPlan(repo_root=args.repo_root)

    if not plan.scripts:
        print("No *.task.sh files changed; writing empty plan.", file=sys.stderr)
        plan.write(args.out)
        return 0

    plan.validate_paths_exist()
    plan.expand_dependencies() # Future-ready stub
    plan.write(args.out)
    plan.print_summary()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[select-doc-pages] ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
