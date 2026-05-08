[CmdletBinding()]
param(
    [string]$AppHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload,
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Help) {
    @"
Usage: .\run.cmd [options] [-- extra uvicorn args]

Options:
  -AppHost HOST    Host to bind, default: 127.0.0.1
  -Port PORT       Port to bind, default: 8000
  -Reload          Enable uvicorn reload
  -Help            Show this help

Examples:
  .\run.cmd
  .\run.cmd -Port 8010 -Reload
"@ | Write-Host
    exit 0
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptRoot

$VenvPython = Join-Path $ScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtualenv was not found. Run .\setup.ps1 first."
}

$UvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $AppHost, "--port", "$Port")
if ($Reload) {
    $UvicornArgs += "--reload"
}
if ($ExtraArgs) {
    $UvicornArgs += $ExtraArgs
}

Write-Host "Starting llmmic at http://${AppHost}:$Port" -ForegroundColor Green
& $VenvPython @UvicornArgs
exit $LASTEXITCODE
