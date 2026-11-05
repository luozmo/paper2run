[CmdletBinding()]
param(
    [string]$InstallDir = "artifacts\dsh-runtime",
    [string]$DshHome = "artifacts\dsh-home-sdk",
    [string]$WorkspaceDir = "artifacts\dsh-workspace",
    [string]$Version = "0.2.1-rc.5"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallPath = if ([System.IO.Path]::IsPathRooted($InstallDir)) { $InstallDir } else { Join-Path $RepoRoot $InstallDir }
$DshHomePath = if ([System.IO.Path]::IsPathRooted($DshHome)) { $DshHome } else { Join-Path $RepoRoot $DshHome }
$WorkspacePath = if ([System.IO.Path]::IsPathRooted($WorkspaceDir)) { $WorkspaceDir } else { Join-Path $RepoRoot $WorkspaceDir }

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-Executable([string]$Name, [string[]]$Fallbacks = @()) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in $Fallbacks) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

$runtimeRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"
$node = Resolve-Executable "node.exe" @(
    (Join-Path $runtimeRoot "node\bin\node.exe"),
    "C:\Program Files\nodejs\node.exe"
)
if (-not $node) { throw "Node.js was not found. Install Node.js 24.9 or newer first." }

$nodeVersionText = (& $node --version).Trim()
$nodeVersion = [version]($nodeVersionText.TrimStart("v").Split("-")[0])
if ($nodeVersion -lt [version]"24.9.0") {
    throw "Node.js 24.9 or newer is required. Found $nodeVersionText."
}

$pnpmCommand = $null
$pnpmBaseArgs = @()
$pnpm = Resolve-Executable "pnpm.cmd" @((Join-Path $runtimeRoot "bin\fallback\pnpm.cmd"))
if (-not $pnpm) { $pnpm = Resolve-Executable "pnpm" }
if ($pnpm) {
    $pnpmCommand = $pnpm
} else {
    $corepack = Resolve-Executable "corepack.cmd" @((Join-Path $runtimeRoot "node\bin\corepack.cmd"))
    if (-not $corepack) { $corepack = Resolve-Executable "corepack" }
    if ($corepack) {
        Write-Step "Enabling pnpm through corepack"
        & $corepack prepare pnpm@11.28.5 --activate
        if ($LASTEXITCODE -ne 0) { throw "Failed to activate pnpm through corepack." }
        $pnpmCommand = $corepack
        $pnpmBaseArgs = @("pnpm")
    } else {
        $npx = Resolve-Executable "npx.cmd" @((Join-Path $runtimeRoot "node\npx.cmd"))
        if (-not $npx) { $npx = Resolve-Executable "npx" }
        if (-not $npx) { throw "pnpm, corepack and npx were not found." }
        $pnpmCommand = $npx
        $pnpmBaseArgs = @("--yes", "pnpm@11.28.5")
    }
}

function Invoke-Pnpm {
    param([string[]]$Arguments)
    $effectiveArgs = @($pnpmBaseArgs) + $Arguments
    & $pnpmCommand @effectiveArgs
    if ($LASTEXITCODE -ne 0) { throw "pnpm command failed: $($Arguments -join ' ')" }
}

Write-Step "Creating DSH directories"
New-Item -ItemType Directory -Force -Path $InstallPath | Out-Null
New-Item -ItemType Directory -Force -Path $DshHomePath | Out-Null
New-Item -ItemType Directory -Force -Path $WorkspacePath | Out-Null

$packagePath = Join-Path $InstallPath "package.json"
@{ private = $true; type = "module" } |
    ConvertTo-Json |
    Set-Content -LiteralPath $packagePath -Encoding utf8

$pnpmWorkspacePath = Join-Path $InstallPath "pnpm-workspace.yaml"
@(
    "allowBuilds:"
    "  '@deepseek-ai/dsh-subprocess-local': true"
    "  '@google/genai': true"
    "  koffi: true"
    "  node-pty: true"
    "  protobufjs: true"
) -join "`n" | Set-Content -LiteralPath $pnpmWorkspacePath -Encoding utf8

Push-Location $InstallPath
try {
    Write-Step "Installing @deepseek-ai/dsh@$Version"
    Invoke-Pnpm -Arguments @("add", "@deepseek-ai/dsh@$Version")

    Write-Step "Rebuilding native dependencies"
    Invoke-Pnpm -Arguments @("rebuild")
} finally {
    Pop-Location
}

$dshBin = Join-Path $InstallPath "node_modules\.bin\dsh.cmd"
if (-not (Test-Path -LiteralPath $dshBin)) { throw "DSH executable was not created: $dshBin" }

Write-Step "Checking installed DSH version"
$env:DSH_HOME = $DshHomePath
$installedVersion = (& $dshBin --version).Trim()
if ($LASTEXITCODE -ne 0) { throw "DSH version check failed." }
if ($installedVersion -ne $Version) {
    throw "Unexpected DSH version. Expected $Version, found $installedVersion."
}

Write-Host ""
Write-Host "DSH setup completed successfully." -ForegroundColor Green
Write-Host "Install directory: $InstallPath"
Write-Host "DSH home:         $DshHomePath"
Write-Host "Workspace:        $WorkspacePath"
Write-Host "DSH version:      $installedVersion"
Write-Host ""
Write-Host "Next step: create $DshHomePath\.credentials.yaml with:"
Write-Host 'version: 1'
Write-Host 'refs:'
Write-Host '  DEEPSEEK_API_KEY: "sk-your-key"'