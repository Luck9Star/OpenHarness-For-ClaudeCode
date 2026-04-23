---
name: harness-dream
description: Offline memory consolidation for OpenHarness. Analyzes execution patterns, consolidates knowledge files, prunes stale state. Run during idle periods via a separate /loop.
---

# Harness Dream | Memory Consolidation

This skill performs offline maintenance on the OpenHarness workspace. It should only run when the workspace is idle, complete, or blocked — never during active execution.

## Preconditions

Before proceeding, verify that the workspace state is NOT `running`:

```bash
python3 scripts/state-manager.py read
```

If `status` is `running`, stop immediately with the message:

> Cannot dream while workspace is running. Wait for the current iteration to complete.

Allowed states for dreaming: `idle`, `failed`, `completed`, `blocked`, `mission_complete`.

## Workflow

### Phase 1: Pattern Analysis

Scan the execution log for patterns in the last 24 hours:

```bash
# Read recent log entries (last 24h worth)
grep -E "^\[" logs/execution_stream.log | tail -200
```

Look for:
- Recurring error types and their frequencies
- Steps that consistently succeed vs. fail
- Average time between iterations
- Common verification failures

### Phase 2: Knowledge Consolidation

Scan the `knowledge/` directory (if it exists):

1. Read each `.md` file in `knowledge/`
2. Identify duplicate or overlapping content
3. Merge related files into consolidated entries
4. Update the Knowledge Index in `.claude/harness-state.local.md` to reflect the new structure
5. Remove empty or placeholder knowledge files

When merging:
- Keep the most detailed version of each piece of information
- Preserve source references and timestamps
- Update cross-references between files

### Phase 3: State Pruning

Trim stale entries from the state file to keep it under 2KB:

1. Read `.claude/harness-state.local.md`
2. Check the Knowledge Index section
3. Remove entries for knowledge files that no longer exist
4. Remove resolved or obsolete pointers
5. Ensure the frontmatter stays compact

After pruning, verify the file size:

```bash
wc -c .claude/harness-state.local.md
```

If still over 2KB, trim the Knowledge Index table to only the most recent 5 entries and add a note: `> Full index available in knowledge/index.md`

### Phase 4: Insight Extraction

Based on the patterns found in Phase 1, extract actionable insights:

1. For each recurring pattern, write a one-line "Distilled Insight"
2. Append these insights to `playbook.md` under a new section:

```markdown
## Distilled Insights

> Auto-extracted by harness-dream on [date]

- [Insight 1]: [Brief description of the pattern and recommended behavior]
- [Insight 2]: [Brief description]
```

If `playbook.md` already has a "Distilled Insights" section, merge new insights with existing ones (avoid duplicates).

### Phase 5: Dream Journal

Write a dream journal entry to `logs/dream_journal.md`:

```markdown
## Dream Entry — [timestamp]

### Patterns Observed
- [Summary of patterns from Phase 1]

### Knowledge Consolidated
- [Summary of merges from Phase 2]

### State Pruned
- [What was removed/trimmed in Phase 3]

### Insights Added
- [New insights from Phase 4]

### State File Size
- [Current size in bytes]
```

### Phase 6: Final Verification

1. Verify `.claude/harness-state.local.md` is under 2KB
2. Verify `logs/dream_journal.md` was updated
3. Verify no knowledge files were deleted without consolidation
4. Report a summary of what was done

## Important Notes

- Dream mode is **read-mostly**. It should minimize writes, and never modify source code or tests.
- The state file size limit (2KB) is a hard constraint. If pruning cannot get it under 2KB, escalate in the dream journal.
- Dream mode does NOT change the workspace status. It leaves the state exactly as it found it (except for the Knowledge Index pruning).
- This skill is designed to be run periodically via `/loop 30m /harness-dream` during idle periods.
