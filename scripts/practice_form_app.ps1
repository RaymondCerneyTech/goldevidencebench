param(
    [string]$OutputPath = "",
    [string]$WindowTitle = "GoldEvidenceBench Practice Form"
)

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputPath = Join-Path $env:TEMP "practice_form_$timestamp.txt"
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = $WindowTitle
$form.Width = 420
$form.Height = 260
$form.StartPosition = "CenterScreen"

$labelUser = New-Object System.Windows.Forms.Label
$labelUser.Text = "Username:"
$labelUser.AutoSize = $true
$labelUser.Location = New-Object System.Drawing.Point(20, 20)

$textUser = New-Object System.Windows.Forms.TextBox
$textUser.Width = 260
$textUser.Location = New-Object System.Drawing.Point(120, 18)
$textUser.TabIndex = 0

$labelPass = New-Object System.Windows.Forms.Label
$labelPass.Text = "Password:"
$labelPass.AutoSize = $true
$labelPass.Location = New-Object System.Drawing.Point(20, 60)

$textPass = New-Object System.Windows.Forms.TextBox
$textPass.Width = 260
$textPass.Location = New-Object System.Drawing.Point(120, 58)
$textPass.UseSystemPasswordChar = $true
$textPass.TabIndex = 1

$checkRemember = New-Object System.Windows.Forms.CheckBox
$checkRemember.Text = "Remember me"
$checkRemember.AutoSize = $true
$checkRemember.Location = New-Object System.Drawing.Point(120, 95)
$checkRemember.TabIndex = 2

$buttonSave = New-Object System.Windows.Forms.Button
$buttonSave.Text = "&Save"
$buttonSave.Width = 80
$buttonSave.Location = New-Object System.Drawing.Point(120, 130)
$buttonSave.TabIndex = 3

$labelStatus = New-Object System.Windows.Forms.Label
$labelStatus.Text = "Status: Ready"
$labelStatus.AutoSize = $true
$labelStatus.Location = New-Object System.Drawing.Point(20, 170)
$labelStatus.TabIndex = 4

$buttonSave.Add_Click({
    $dir = Split-Path $OutputPath -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $content = @(
        "username=$($textUser.Text)"
        "password=$($textPass.Text)"
        "remember=$($checkRemember.Checked)"
    ) -join "`n"
    Set-Content -Path $OutputPath -Value $content -Encoding UTF8
    $labelStatus.Text = "Saved: $OutputPath"
})

$form.AcceptButton = $buttonSave
$form.Controls.AddRange(@(
    $labelUser,
    $textUser,
    $labelPass,
    $textPass,
    $checkRemember,
    $buttonSave,
    $labelStatus
))

$null = $textUser.Focus()
[void]$form.ShowDialog()
