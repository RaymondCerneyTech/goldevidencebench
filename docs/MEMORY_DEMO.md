# Memory Demo

Memory claims must be backed by citations.
Memories are verified at read time; invalid citations must trigger abstain.
Use exact substrings in claim_text to keep verification deterministic.

## Notes-backed memory (optional)

You can treat a notes file as a cheap, persistent memory source by appending
notes and emitting citation-backed memory entries.

Add a note and create a memory entry:

```powershell
python .\scripts\add_note_memory.py --note "Project status: all trap families green."
```

By default notes are tagged `notes,project`. Override with `--tags`.

Verify notes-backed memories:

```powershell
python .\scripts\verify_memories.py --in .\data\memories\user_notes_memory.jsonl `
  --out .\runs\release_gates\memory_verify.json `
  --out-details .\runs\release_gates\memory_verify_details.json
```

Retrieve verified notes:

```powershell
python .\scripts\get_verified_notes.py --limit 5
```

Filter verified notes by query:

```powershell
python .\scripts\get_verified_notes.py --query "trap families" --limit 5
```

Filter verified notes by tag:

```powershell
python .\scripts\get_verified_notes.py --tag project --limit 5
```

Newest-first view:

```powershell
python .\scripts\get_verified_notes.py --latest --limit 5
```
