param(
    [Parameter(Mandatory = $true)]
    [string]$Claim,
    [string]$Tags = "notes,project",
    [double]$Confidence = 0.6,
    [switch]$Unused,
    [string]$NotesPath = "data/memories/user_notes.txt",
    [string]$MemoryPath = "data/memories/user_notes_memory.jsonl"
)

$ErrorActionPreference = "Stop"

python .\scripts\add_note_memory.py --note $Claim --tags $Tags --confidence $Confidence --notes-path $NotesPath --memory-path $MemoryPath @(
    if ($Unused) { "--unused" }
)
