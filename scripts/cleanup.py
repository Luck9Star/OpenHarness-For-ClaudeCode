#!/usr/bin/env python3
"""OpenHarness Entropy Control.

Compresses logs, prunes old progress records, enforces state file size limits.
Run periodically via the loop prompt.

Usage:
    cleanup.py [--all] [--logs] [--progress] [--state] [--temp]
"""

import sys
import gzip
import shutil
import json
import re
from datetime import datetime
from pathlib import Path

# Configuration
LOG_ROTATE_SIZE = 10 * 1024 * 1024   # 10MB
PROGRESS_KEEP_RUNS = 50
MAX_STATE_SIZE = 2048                  # 2KB

# State file location
STATE_FILE = ".claude/harness-state.json"
LOG_FILE = ".claude/harness/logs/execution_stream.log"
PROGRESS_FILE = ".claude/harness/progress.md"
DREAM_JOURNAL = ".claude/harness/logs/dream_journal.md"
ARCHIVE_DIR = ".claude/harness/archive"

# Temp file patterns to clean
TEMP_PATTERNS = ["*.tmp", "*.bak", "*.swp", "*~", ".DS_Store"]


def report(category, message):
    """Print a cleanup report line."""
    print(f"  [{category}] {message}")


def cleanup_logs(base_path):
    """Rotate execution_stream.log if it exceeds the size threshold."""
    log_path = base_path / LOG_FILE
    if not log_path.exists():
        report("logs", "No execution log found — nothing to do.")
        return

    size = log_path.stat().st_size
    if size < LOG_ROTATE_SIZE:
        size_mb = size / (1024 * 1024)
        report("logs", f"Log file is {size_mb:.1f}MB — under 10MB threshold, no rotation needed.")
        return

    # Rotate: compress current log to timestamped .gz
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    compressed_name = f"execution_stream-{timestamp}.log.gz"
    compressed_path = log_path.parent / compressed_name

    with open(log_path, 'rb') as f_in:
        with gzip.open(compressed_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    # Truncate the original log (keep header)
    original_size = size
    log_path.write_text(f"# Execution Stream Log\n# Rotated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    compressed_size = compressed_path.stat().st_size
    ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
    report("logs", f"Rotated log ({original_size / 1024 / 1024:.1f}MB -> {compressed_size / 1024:.1f}KB gzipped, {ratio:.0f}% savings)")
    report("logs", f"Archive: {compressed_path}")


def cleanup_progress(base_path):
    """Prune progress.md entries older than PROGRESS_KEEP_RUNS runs."""
    progress_path = base_path / PROGRESS_FILE
    if not progress_path.exists():
        report("progress", "No progress file found — nothing to do.")
        return

    text = progress_path.read_text()

    # Find all run entries (### Run #NNN)
    runs = list(re.finditer(r'(### Run #(\d+).*?)(?=### Run #|\Z)', text, re.DOTALL))

    if not runs:
        report("progress", "No run entries found — nothing to prune.")
        return

    total_runs = len(runs)
    if total_runs <= PROGRESS_KEEP_RUNS:
        report("progress", f"Only {total_runs} run entries — under threshold of {PROGRESS_KEEP_RUNS}, no pruning needed.")
        return

    # Keep only the last PROGRESS_KEEP_RUNS entries
    runs_to_keep = runs[-PROGRESS_KEEP_RUNS:]
    runs_to_prune = runs[:-PROGRESS_KEEP_RUNS]
    first_kept = runs_to_keep[0]

    # Build a summary of pruned entries
    pruned_runs = []
    for match in runs_to_prune:
        run_num = match.group(2)
        # Extract result if available
        result_match = re.search(r'\|\s*Result\s*\|\s*`?([^`|\n]+)`?\s*\|', match.group(1))
        result = result_match.group(1).strip() if result_match else "unknown"
        pruned_runs.append(f"Run #{run_num}: {result}")

    # Rebuild the progress file
    header_match = re.match(r'(.*?)(### Run #)', text, re.DOTALL)
    header = header_match.group(1) if header_match else text.split("### Run #")[0]

    # Add a summary of pruned runs
    success_count = sum(1 for r in pruned_runs if "success" in r.lower())
    fail_count = sum(1 for r in pruned_runs if "fail" in r.lower())

    summary = (
        f"\n<!-- Pruned {len(pruned_runs)} runs older than Run #{first_kept.group(2)} "
        f"({success_count} successes, {fail_count} failures) -->\n\n"
    )

    # Get remaining body (from first kept run onwards)
    remaining_body = text[first_kept.start():]

    new_text = header + summary + remaining_body
    progress_path.write_text(new_text)

    report("progress", f"Pruned {len(pruned_runs)} old entries (kept last {PROGRESS_KEEP_RUNS})")
    report("progress", f"Summary: {success_count} successes, {fail_count} failures removed")


def cleanup_state(base_path):
    """Enforce state file size limit by trimming the knowledge index."""
    state_path = base_path / STATE_FILE
    if not state_path.exists():
        report("state", "No state file found — nothing to do.")
        return

    size = state_path.stat().st_size
    if size <= MAX_STATE_SIZE:
        report("state", f"State file is {size} bytes — under {MAX_STATE_SIZE} byte limit.")
        return

    try:
        with open(state_path) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        report("state", f"Cannot parse state file: {e}. Skipping.")
        return

    # Try trimming the knowledge_index list if present
    knowledge_index = state.get("knowledge_index", [])
    if knowledge_index and len(knowledge_index) > 3:
        original_count = len(knowledge_index)
        state["knowledge_index"] = knowledge_index[-3:]  # Keep last 3 entries

        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")

        new_size = state_path.stat().st_size
        report("state", f"Trimmed knowledge index: {original_count} -> 3 entries ({size} -> {new_size} bytes)")
        if new_size > MAX_STATE_SIZE:
            report("state", f"WARNING: State file still over {MAX_STATE_SIZE} bytes after trimming. Manual intervention needed.")
    else:
        report("state", "Knowledge index has few entries or is absent. Cannot trim further.")


def cleanup_temp(base_path):
    """Clean up temporary files in the workspace."""
    cleaned = 0
    for pattern in TEMP_PATTERNS:
        for f in base_path.rglob(pattern):
            # Don't delete temp files in .git
            if '.git' in str(f):
                continue
            try:
                f.unlink()
                report("temp", f"Removed: {f.relative_to(base_path)}")
                cleaned += 1
            except OSError:
                pass

    if cleaned == 0:
        report("temp", "No temporary files found.")
    else:
        report("temp", f"Cleaned {cleaned} temporary file(s).")


def cleanup_archives(base_path):
    """Keep only the last 5 archive directories, deleting older ones."""
    archive_path = base_path / ARCHIVE_DIR
    if not archive_path.exists():
        report("archives", "No archive directory found — nothing to do.")
        return

    archives = sorted(
        [d for d in archive_path.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
    )

    if len(archives) <= 5:
        report("archives", f"{len(archives)} archive(s) found — under limit of 5, no pruning needed.")
        return

    to_delete = archives[:-5]
    for d in to_delete:
        shutil.rmtree(d)
        report("archives", f"Deleted old archive: {d.name}")

    report("archives", f"Pruned {len(to_delete)} old archive(s), kept {len(archives) - len(to_delete)}.")


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    base_path = Path.cwd()

    # Parse arguments
    do_all = "--all" in args or not args
    do_logs = do_all or "--logs" in args
    do_progress = do_all or "--progress" in args
    do_state = do_all or "--state" in args
    do_temp = do_all or "--temp" in args
    do_archives = do_all or "--archives" in args

    # Warn about unrecognized flags
    known = {"--all", "--logs", "--progress", "--state", "--temp", "--archives", "--help", "-h"}
    unrecognized = [a for a in args if a.startswith("-") and a not in known]
    if unrecognized:
        print(f"Warning: Unrecognized arguments: {' '.join(unrecognized)}", file=sys.stderr)

    print(f"=== OpenHarness Cleanup Report ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print()

    if do_logs:
        print("[logs] Checking execution log...")
        cleanup_logs(base_path)
        print()

    if do_progress:
        print("[progress] Checking progress history...")
        cleanup_progress(base_path)
        print()

    if do_state:
        print("[state] Checking state file size...")
        cleanup_state(base_path)
        print()

    if do_temp:
        print("[temp] Checking for temporary files...")
        cleanup_temp(base_path)
        print()

    if do_archives:
        print("[archives] Checking old archives...")
        cleanup_archives(base_path)
        print()

    print("=== Cleanup Complete ===")


if __name__ == "__main__":
    main()
