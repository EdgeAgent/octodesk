# OctoDesk one-shot setup (Windows): venv + install + desktop shortcut.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
py -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install --quiet --upgrade pip
pip install --quiet -e .

$shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "OctoDesk.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $PSScriptRoot ".venv\Scripts\octodesk.exe"
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "OctoDesk - Release the Kraken (paper only)"
$shortcut.Save()

Write-Host ""
Write-Host "OctoDesk installed. A shortcut is on your Desktop."
Write-Host "Or run:  .\.venv\Scripts\octodesk.exe   then open http://127.0.0.1:8917"
Write-Host "Offline check any time:  octodesk demo"
