param(
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [switch]$OverwriteFixtures,
    [ValidateSet("observe", "ramp", "target", "custom")]
    [string]$Stage = "observe",
    [double]$CanaryAlertExactRate = 0.90
)

& .\scripts\run_control_family_scaffold.ps1 `
    -Family "intent_spec_layer" `
    -OutRoot $OutRoot `
    -ModelPath $ModelPath `
    -Adapter $Adapter `
    -Protocol $Protocol `
    -MaxSupportK $MaxSupportK `
    -OverwriteFixtures:$OverwriteFixtures `
    -Stage $Stage `
    -CanaryAlertExactRate $CanaryAlertExactRate

exit $LASTEXITCODE
