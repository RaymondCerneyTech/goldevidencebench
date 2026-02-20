param(
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [switch]$OverwriteFixtures,
    [switch]$UseRealPublicFixtures,
    [ValidateSet("observe", "ramp", "target", "custom")]
    [string]$Stage = "observe",
    [double]$CanaryAlertExactRate = 0.90,
    [switch]$FailOnCanaryWarn,
    [switch]$FailFast,
    [bool]$RunPersonaTrap = $true,
    [string]$PersonaProfiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful"
)

& .\scripts\run_control_family_scaffold.ps1 `
    -Family "agency_preserving_substitution" `
    -OutRoot $OutRoot `
    -ModelPath $ModelPath `
    -Adapter $Adapter `
    -Protocol $Protocol `
    -MaxSupportK $MaxSupportK `
    -OverwriteFixtures:$OverwriteFixtures `
    -UseRealPublicFixtures:$UseRealPublicFixtures `
    -Stage $Stage `
    -CanaryAlertExactRate $CanaryAlertExactRate `
    -FailOnCanaryWarn:$FailOnCanaryWarn `
    -FailFast:$FailFast `
    -RunPersonaTrap $RunPersonaTrap `
    -PersonaProfiles $PersonaProfiles

exit $LASTEXITCODE
