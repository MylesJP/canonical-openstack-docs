#!/usr/bin/env python3
"""
select-doc-pages.py

Builds an ordered execution plan of snippet scripts to run for docs CI.

Inputs:
  --changed-file-list  Path to a newline-delimited list of changed files
  --out                Path to write the newline-delimited execution plan

Behavior (v1, minimal):
  * Reads changed files, filters to *.task.sh
  * Validates existence on disk
  * De-duplicates while preserving order
  * (Stub) Placeholder for recursive @depends expansion (no-op for now)
  * Writes the final plan, one path per line, to --out

Exit codes:
  0 on success, >0 on failure
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Iterable, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Select doc snippet pages to run.")
    p.add_argument(
        "--changed-file-list",
        required=True,
        help="Path to a newline-delimited file of changed files.",
    )
    p.add_argument(
        "--out",
        required=True,
        help="Path to write the newline-delimited execution plan.",
    )
    p.add_argument(
        "--repo-root",
        default=".",
        help="Optional repository root (for nicer logging); default='.'.",
    )
    return p.parse_args()


def read_lines(path: Path) -> List[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Changed file list not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        # Keep raw lines, strip later
        return [ln.rstrip("\n") for ln in f]


def is_task_snippet(path_str: str) -> bool:
    # Only act on snippet task files per spec: *.task.sh
    return path_str.endswith(".task.sh")


def normalize(path_str: str) -> str:
    # Normalize to repo-relative POSIX-style paths for stable logs/plan
    p = Path(path_str).resolve()
    try:
        repo = Path.cwd().resolve()
        rel = p.relative_to(repo)
    except Exception:
        rel = p
    return rel.as_posix()


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def validate_paths_exist(paths: Iterable[str]) -> None:
    missing = [p for p in paths if not Path(p).is_file()]
    if missing:
        joined = "\n  - ".join(missing)
        raise FileNotFoundError(
            f"The following snippet files do not exist:\n  - {joined}"
        )


def parse_depends_headers(script_path: str) -> List[str]:
    """
    (Optional helper for later)
    Parse simple '@depends' comment blocks like:

      # @depends:
      #   - tutorial/snippets/get-started-with-openstack.task.sh
      #   - how-to/snippets/feature-observability.task.sh

    Returns a list of dependency paths as written (not resolved).

    CURRENTLY UNUSED in v1 (kept as a helper for the future).
    """
    deps: List[str] = []
    try:
        with open(script_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return deps

    in_block = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("# @depends"):
            in_block = True
            continue
        if in_block:
            if s.startswith("#") and "-" in s:
                # e.g. "#   - path/to/script.task.sh"
                # Extract after '-' and strip
                try:
                    dep = s.split("-", 1)[1].strip()
                    if dep:
                        deps.append(dep)
                except Exception:
                    pass
            elif not s.startswith("#"):
                # End of block when non-comment encountered
                break
    return deps


def expand_with_dependencies(initial_scripts: List[str]) -> List[str]:
    """
    STUB IMPLEMENTATION (v1):
    -------------------------
    For now, we DO NOT perform recursive @depends expansion.
    We simply return the incoming list, de-duplicated and validated.

    TODO (v2+):
      - For each script, read its @depends block (parse_depends_headers)
      - Resolve each dependency path relative to the script’s directory (or repo root)
      - Recursively expand and topo-sort, detect cycles, and de-dupe
      - Ensure dependencies appear BEFORE their dependents in the plan
    """
    return unique_preserve_order(initial_scripts)


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    os.chdir(repo_root)

    changed_path = Path(args.changed_file_list)
    out_path = Path(args.out)

    raw_lines = read_lines(changed_path)

    # Trim and drop empties
    changed = [ln.strip() for ln in raw_lines if ln.strip()]
    if not changed:
        # Nothing changed: write empty plan and exit 0
        out_path.write_text("", encoding="utf-8")
        print("No changed files provided; wrote empty plan.", file=sys.stderr)
        return 0

    # Keep *.task.sh only
    task_snippets = [p for p in changed if is_task_snippet(p)]

    # If there are no snippet files in the change set, emit empty plan and succeed
    if not task_snippets:
        out_path.write_text("", encoding="utf-8")
        print("No *.task.sh files changed; wrote empty plan.", file=sys.stderr)
        return 0

    # Normalize to repo-relative POSIX paths for deterministic output
    normalized = [normalize(p) for p in task_snippets]
    normalized = unique_preserve_order(normalized)

    # Ensure files exist (fast feedback when globs/paths are off)
    validate_paths_exist(normalized)

    # (Stub) Dependency expansion — currently a no-op that preserves order & uniqueness
    plan = expand_with_dependencies(normalized)

    # Write plan
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for p in plan:
            f.write(f"{p}\n")

    # Optional: print plan in logs for convenience
    print("Execution plan:", file=sys.stderr)
    for i, p in enumerate(plan, 1):
        print(f"  [{i:02d}] {p}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[select-doc-pages] ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
