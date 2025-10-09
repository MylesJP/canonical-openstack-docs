#!/usr/bin/env python3
"""
run-doc-pages.py

Executor for docs snippets plan. This script extracts and runs shell commands
found within special comment blocks (`[docs-exec:<name>] ... [docs-exec:<name>-end]`)
in scripts. If no such blocks are found in a script, the step fails.

Usage:
  python ci/run-doc-pages.py --plan plan.txt

Environment:
  DOCS_DRY_RUN=1   -> Print the plan and validate blocks, but do not execute.

Plan format:
  Newline-delimited file where each line is a path to a *.task.sh script.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from subprocess import run, CalledProcessError  # nosec B404

# --------- CLI --------- #

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run docs snippet plan sequentially.")
    p.add_argument(
        "--plan",
        required=True,
        type=Path,
        help="Path to a newline-delimited file of scripts to run (execution order).",
    )
    return p.parse_args()

def read_plan(plan_path: Path) -> list[Path]:
    if not plan_path.is_file():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    raw = plan_path.read_text(encoding="utf-8", errors="ignore")
    lines = plan_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [Path(p.strip()) for p in lines if p.strip() and not p.lstrip().startswith("#")]

def require_files_exist(paths: list[Path]) -> None:
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError("Script(s) in plan not found:\n  - " + "\n  - ".join(missing))

EXEC_BEGIN_RE = re.compile(r'^\s*#\s*\[docs-exec:([^\]]+)\]\s*$')
EXEC_END_FMT = r'^\s*#\s*\[docs-exec:%s-end\]\s*$'

@dataclass
class ExtractedScript:
    text: str               # runnable bash text (with shebang + set -euo pipefail)
    used_exec_blocks: bool  # whether any exec blocks were found
    block_names: list[str]  # names of the blocks included

def build_ci_text_from_exec_blocks(script_path: Path) -> ExtractedScript:
    """
    Parse script and concatenate all [docs-exec:<name>]...[docs-exec:<name>-end] blocks.
    If one or more exec blocks are found, returns a Bash script consisting of those blocks.
    Otherwise returns used_exec_blocks=False.
    """
    try:
        src_lines = script_path.read_text(encoding="utf-8", errors="ignore").splitlines(True)
    except OSError as e:
        raise OSError(f"Failed to read script file {script_path}: {e}") from e

    out_chunks: list[str] = []
    names: list[str] = []

    lines_iter = iter(src_lines)
    for line in lines_iter:
        m = EXEC_BEGIN_RE.match(line)
        if not m:
            continue

        name = m.group(1).strip()
        names.append(name)
        end_re = re.compile(EXEC_END_FMT % re.escape(name))

        block: list[str] = []
        for block_line in lines_iter:
            if end_re.match(block_line):
                break
            block.append(block_line)
        else:
            # loop exhausted: no end marker
            print(f"Warning: missing [docs-exec:{name}-end] in {script_path}", file=sys.stderr)

        out_chunks.append("".join(block))

    if names:
        header = "#!/usr/bin/env bash\nset -euo pipefail\n"
        return ExtractedScript(
            text=header + "\n".join(out_chunks),
            used_exec_blocks=True,
            block_names=names,
        )

    return ExtractedScript(text="", used_exec_blocks=False, block_names=[])

def run_script_text(text: str, cwd: Path) -> int:
    """
    Execute the given bash text by piping it to bash's stdin.
    Returns the exit code.
    """
    try:
        completed = run(  # nosec B603
            ["bash"], input=text, text=True, cwd=str(cwd), check=False
        )
        return completed.returncode
    except CalledProcessError as e:
        return e.returncode

def main() -> int:
    args = parse_args()
    scripts = read_plan(args.plan)

    if not scripts:
        print("Plan is empty. Nothing to run.")
        return 0

    require_files_exist(scripts)
    dry_run = os.environ.get("DOCS_DRY_RUN") == "1"

    print("\n--- Documentation Test Execution ---")
    print(f"Total steps: {len(scripts)}\n")

    # Parse once and cache results of [docs-exec:*] extraction
    extracted: list[tuple[Path, ExtractedScript]] = []
    print("[PLAN] Execution plan:")
    for i, script in enumerate(scripts, start=1):
        ex = build_ci_text_from_exec_blocks(script)
        extracted.append((script, ex))
        using = f"docs-exec: {', '.join(ex.block_names)}" if ex.used_exec_blocks else "NO docs-exec FOUND"
        print(f"  [{i:02d}] {script}  | {using}")
    print("")  # blank line

    if dry_run:
        print("[DRY RUN] Skipping execution per DOCS_DRY_RUN=1.")
        return 0

    # Execute each plan item using cached extraction
    for i, (script, ex) in enumerate(extracted, start=1):
        print(f"==> [Step {i}/{len(scripts)}] {script}")

        if not ex.used_exec_blocks:
            print(f"\n[run-doc-pages] FAILURE: No [docs-exec:*] blocks found in {script}.")
            print("    Each script in the plan must contain at least one executable docs block.")
            return 1  # non-zero to fail the job

        sect_disp = ", ".join(ex.block_names)
        print(f"    using: docs-exec blocks -> {sect_disp}\n")

        rc = run_script_text(ex.text, cwd=script.parent)
        if rc != 0:
            print(f"\n[run-doc-pages] FAILURE at step {i}: {script} executed with non-zero exit code ({rc})")
            return rc

        print(f"\n--- [Step {i}/{len(scripts)}] SUCCESS: {script} ---\n")

    print("All steps in the execution plan completed successfully.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[run-doc-pages] Interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"[run-doc-pages] ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
