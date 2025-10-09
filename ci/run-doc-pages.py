#!/usr/bin/env python3
"""
run-doc-pages.py

Executor for docs snippets plan. This script extracts and runs shell commands
found within special comment blocks (`[docs-exec]...`) in scripts. If no such
[docs-exec] blocks are found in a script, return an error.

Manual usage:
  python ci/run-doc-pages.py --plan plan.txt

Environment:
  PRINT_PLAN=1   -> Print what would run without executing.

Plan format:
  Newline-delimited file where each line is a path to a *.task.sh script.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen

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


# --------- Plan utilities --------- #

def read_plan(plan_path: Path) -> list[Path]:
    if not plan_path.is_file():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    raw = plan_path.read_text(encoding="utf-8", errors="ignore")
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return [Path(p.strip()) for p in lines if p.strip() and not p.lstrip().startswith("#")]


def require_files_exist(paths: list[Path]) -> None:
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Script(s) in plan not found:\n  - " + "\n  - ".join(missing)
        )


# --------- docs-exec block extraction --------- #

EXEC_BEGIN_RE = re.compile(r'^\s*#\s*\[docs-exec:([^\]]+)\]\s*$')
EXEC_END_FMT = r'^\s*#\s*\[docs-exec:%s-end\]\s*$'

@dataclass
class ExtractedScript:
    text: str
    used_exec_blocks: bool
    block_names: list[str]

def build_ci_text_from_exec_blocks(script_path: Path) -> ExtractedScript:
    """
    Parse script and concatenate all [docs-exec:<name>]...[docs-exec:<name>-end] blocks.
    - If one or more exec blocks are found, returns a Bash script consisting of those blocks.
    - If none found, returns a result indicating no blocks were used.
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
            block_names=names
        )

    # No blocks found
    return ExtractedScript(text="", used_exec_blocks=False, block_names=[])


def make_executable_copy(script: Path) -> tuple[Path, ExtractedScript]:
    """
    Create a temp script to execute.
    Returns (temp_path, extraction_details).
    """
    extraction = build_ci_text_from_exec_blocks(script)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".sh") as tmp:
        tmp.write(extraction.text)
        temp_path = Path(tmp.name)
    os.chmod(temp_path, 0o755)  # optional
    return temp_path, extraction

# --------- Runner --------- #

def run_script(script: Path) -> int:
    """
    Executes the script via bash, streaming its output and waiting for completion.
    Returns the exit code.
    """
    script = script.resolve()
    cmd = ["bash", str(script)]

    proc = Popen(
        cmd,
        cwd=script.parent,
        preexec_fn=os.setsid,
    )

    return proc.wait()


# --------- Main --------- #

def main() -> int:
    args = parse_args()
    scripts = read_plan(args.plan)

    if not scripts:
        print("Plan is empty. Nothing to run.")
        return 0

    require_files_exist(scripts)
    dry_run = os.environ.get("PRINT_PLAN") == "1"

    print("\n--- Documentation Test Execution ---")
    print(f"Total steps: {len(scripts)}\n")

    if dry_run:
        print("[DRY RUN] Execution plan:")
        for i, script in enumerate(scripts, start=1):
            extraction = build_ci_text_from_exec_blocks(script)
            using = f"docs-exec: {', '.join(extraction.block_names)}" if extraction.used_exec_blocks else "NO docs-exec FOUND"
            print(f"  [{i:02d}] {script}  | {using}")
        return 0

    for i, script in enumerate(scripts, start=1):
        print(f"==> [Step {i}/{len(scripts)}] {script}")

        prepared_path, extraction = make_executable_copy(script)

        if not extraction.used_exec_blocks:
            print(f"\n[run-doc-pages] FAILURE: No [docs-exec:*] blocks found in {script}.")
            print("    Each script in the plan must contain at least one executable docs block.")
            with contextlib.suppress(OSError):
                os.unlink(prepared_path)
            return 1 # Return a non-zero exit code

        sect_disp = ", ".join(extraction.block_names)
        print(f"    using: docs-exec blocks -> {sect_disp}\n")

        try:
            rc = run_script(prepared_path)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(prepared_path)

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