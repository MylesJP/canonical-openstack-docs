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

Dependency additions:
  In any *.task.sh file, add lines like:
      # @depends tutorial/snippets/get-started-with-openstack.task.sh
  This is useful for features that require a sunbeam installation to use.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from typing import List


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
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


@dataclass
class ExecutionPlan:
    """Represents the set of scripts to be executed."""
    scripts: List[Path] = field(default_factory=list)
    repo_root: Path = Path(".")

    @classmethod
    def from_changed_files(cls, path: Path, repo_root: Path) -> "ExecutionPlan":
        """Create a plan from a file listing changed paths."""
        if not path.is_file():
            raise FileNotFoundError(f"Changed file list not found: {path}")

        raw = path.read_text(encoding="utf-8", errors="ignore")
        # Accept both newline- and whitespace-separated inputs, ignore comments
        tokens = [t for t in re.split(r"\s+", raw.strip()) if t and not t.startswith("#")]
        task_paths = [Path(t) for t in tokens if t.endswith(".task.sh")]
        # Preserve order, drop duplicates
        unique_paths = list(dict.fromkeys(task_paths))

        return cls(scripts=unique_paths, repo_root=repo_root)

    def validate_paths_exist(self) -> None:
        """Ensure all scripts in the plan exist on disk."""
        missing = [str(p) for p in self.scripts if not p.is_file()]
        if missing:
            joined = "\n  - ".join(missing)
            raise FileNotFoundError(f"The following snippet files do not exist:\n  - {joined}")


    _depends_re = re.compile(r"^\s*#\s*@depends\s+(.+?)\s*$")

    def _resolve_dep(self, raw: str, script: Path) -> Path:
        """Resolve a dependency path:
           - '/...'        => absolute
           - './...' or '../...' => relative to script directory
           - otherwise     => relative to repo root
        """
        s = raw.strip().strip("'").strip('"')
        if s.startswith("/"):
            return Path(s).resolve()
        if s.startswith("./") or s.startswith("../"):
            return (script.parent / s).resolve()
        return (self.repo_root / s).resolve()

    def _parse_direct_depends(self, script: Path) -> List[Path]:
        """
        Parse direct dependency lines from a snippet script (one level only).
        Each line format: '# @depends path/to/other.task.sh'
        """
        try:
            text = script.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return []

        deps: List[Path] = []
        for line in text.splitlines():
            m = self._depends_re.match(line)
            if not m:
                continue
            raw = m.group(1)
            # Only consider *.task.sh deps
            if not raw.strip().strip("'").strip('"').endswith(".task.sh"):
                continue
            dep_path = self._resolve_dep(raw, script)
            deps.append(dep_path)

        # Preserve declared order, drop duplicates
        return list(dict.fromkeys(deps))


    def expand_dependencies(self) -> None:
        """
        Insert direct dependencies before each script (no recursion).
        Final order example:
          depA, depB, script1, depC, script2, ...
        De-duplicated while preserving first occurrence.
        """
        ordered: List[Path] = []
        seen: set[Path] = set()

        for script in self.scripts:
            s_abs = script.resolve()

            # Insert direct deps first (one level only)
            for dep in self._parse_direct_depends(s_abs):
                d = dep.resolve()
                if d not in seen:
                    seen.add(d)
                    ordered.append(d)

            # Then the script itself
            if s_abs not in seen:
                seen.add(s_abs)
                ordered.append(s_abs)

        self.scripts = ordered

    def write(self, out_path: Path) -> None:
        """Write the final, normalized plan to a file."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_paths = [normalize_path(p, self.repo_root) for p in self.scripts]
        out_path.write_text("\n".join(normalized_paths) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    try:
        plan = ExecutionPlan.from_changed_files(
            path=args.changed_file_list, repo_root=args.repo_root
        )
    except FileNotFoundError:
        raise
    except Exception:
        plan = ExecutionPlan(repo_root=args.repo_root)

    if not plan.scripts:
        print("No *.task.sh files changed; writing empty plan.", file=sys.stderr)
        plan.write(args.out)
        return 0

    # Validate the changed files we were given, then expand one-level deps,
    # then validate again to catch missing dependency files.
    plan.validate_paths_exist()
    plan.expand_dependencies()
    plan.validate_paths_exist()
    plan.write(args.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[select-doc-pages] ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
