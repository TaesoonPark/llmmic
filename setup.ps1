[CmdletBinding()]
param(
    [string]$PythonVersion = "3.11",
    [string]$VenvPath = ".venv",
    [string]$DockerImage = "llmmic-melotts",
    [string]$DockerContainer = "llmmic-melotts",
    [int]$DockerPort = 8899,
    [switch]$SkipDocker,
    [switch]$SkipDockerBuild,
    [switch]$SkipDockerRun,
    [switch]$SkipPipInstall,
    [switch]$RunSmokeTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-LastExitCode {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage,
        [switch]$Quiet
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) {
            & $FilePath @Arguments 2>&1 | Out-Null
        }
        else {
            & $FilePath @Arguments
        }
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    if ($ExitCode -ne 0) {
        throw $FailureMessage
    }
}

function Invoke-NativeOutput {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Output = & $FilePath @Arguments 2>$null
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    if ($ExitCode -ne 0) {
        throw $FailureMessage
    }
    return $Output
}

function Get-PythonLauncherArgs {
    if (Test-Command "py") {
        return @("py", "-$PythonVersion")
    }
    if (Test-Command "python") {
        return @("python")
    }
    throw "Python was not found. Install Python $PythonVersion and try again."
}

function Invoke-HostPython {
    param([string[]]$Arguments)
    $Launcher = @(Get-PythonLauncherArgs)
    $Executable = $Launcher[0]
    $BaseArgs = @()
    if ($Launcher.Count -gt 1) {
        $BaseArgs = $Launcher[1..($Launcher.Count - 1)]
    }
    $AllArgs = @()
    $AllArgs += $BaseArgs
    $AllArgs += $Arguments
    & $Executable @AllArgs
    Assert-LastExitCode "Python command failed."
}

function Test-HttpReady {
    param([string]$Url)
    try {
        $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        if (Test-HttpReady $Url) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Invoke-VenvPython {
    param([string[]]$Arguments)
    & $VenvPython @Arguments
    Assert-LastExitCode "Virtualenv Python command failed."
}

$VenvFullPath = $VenvPath
if (-not [System.IO.Path]::IsPathRooted($VenvFullPath)) {
    $VenvFullPath = Join-Path $ScriptRoot $VenvFullPath
}
$VenvPython = Join-Path $VenvFullPath "Scripts\python.exe"

Write-Step "Preparing Python virtual environment"
if (-not (Test-Path $VenvPython)) {
    Invoke-HostPython @("-m", "venv", $VenvFullPath)
}
else {
    Write-Host "Using existing venv: $VenvFullPath"
}

if (-not $SkipPipInstall) {
    Write-Step "Installing Python dependencies"
    Invoke-VenvPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-VenvPython @("-m", "pip", "install", "-r", (Join-Path $ScriptRoot "requirements.txt"))
}
else {
    Write-Host "Skipping pip install."
}

$EnvFile = Join-Path $ScriptRoot ".env"
$EnvExample = Join-Path $ScriptRoot ".env.example"
if ((-not (Test-Path $EnvFile)) -and (Test-Path $EnvExample)) {
    Write-Step "Creating .env from .env.example"
    Copy-Item -Path $EnvExample -Destination $EnvFile
}

if (-not $SkipDocker) {
    if (-not (Test-Command "docker")) {
        throw "Docker was not found. Install Docker Desktop or run with -SkipDocker."
    }

    Write-Step "Checking Docker"
    Invoke-NativeCommand -FilePath "docker" -Arguments @("info") -FailureMessage "Docker is not running or is not reachable." -Quiet

    if (-not $SkipDockerBuild) {
        Write-Step "Building MeloTTS Docker image"
        Invoke-NativeCommand -FilePath "docker" -Arguments @("build", "-t", $DockerImage, (Join-Path $ScriptRoot "docker\melotts_service")) -FailureMessage "Docker image build failed."
    }
    else {
        Write-Host "Skipping Docker image build."
    }

    $TtsHealthUrl = "http://127.0.0.1:$DockerPort/health"
    if (-not $SkipDockerRun) {
        Write-Step "Starting MeloTTS Docker service"
        if (Test-HttpReady $TtsHealthUrl) {
            Write-Host "MeloTTS service is already responding at $TtsHealthUrl"
        }
        else {
            $ExistingContainer = Invoke-NativeOutput -FilePath "docker" -Arguments @("ps", "-a", "--filter", "name=^/$DockerContainer$", "--format", "{{.ID}}") -FailureMessage "Failed to inspect Docker containers."
            if ($ExistingContainer) {
                Invoke-NativeCommand -FilePath "docker" -Arguments @("rm", "-f", $DockerContainer) -FailureMessage "Failed to remove existing Docker container."
            }

            Invoke-NativeCommand -FilePath "docker" -Arguments @("run", "-d", "--name", $DockerContainer, "-p", "${DockerPort}:8899", $DockerImage) -FailureMessage "Failed to start MeloTTS Docker container."

            if (-not (Wait-HttpReady $TtsHealthUrl 30)) {
                throw "MeloTTS service did not become ready at $TtsHealthUrl"
            }
        }
    }
    else {
        Write-Host "Skipping Docker container start."
    }
}
else {
    Write-Host "Skipping Docker setup."
}

if ($RunSmokeTests) {
    Write-Step "Running smoke tests"
    Invoke-VenvPython @((Join-Path $ScriptRoot "scripts\check_llm_stream.py"))
    Invoke-VenvPython @((Join-Path $ScriptRoot "scripts\smoke_tts_ko.py"))
    Invoke-VenvPython @((Join-Path $ScriptRoot "scripts\simulate_ws_session.py"))
    Invoke-VenvPython @("-m", "pytest")
}

Write-Step "Ready"
Write-Host "Start the app with:"
Write-Host ".\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000" -ForegroundColor Green
