<#
.SYNOPSIS
  SessionGuardian installer for Windows (PowerShell 5.1+).

.DESCRIPTION
  EXPERIMENTAL: written to mirror install.sh but not yet validated on a Windows machine.
  It is exercised by the windows-latest CI job (.github/workflows/tests.yml).

  Safe to re-run: upgrades in place, never overwrites modified skills or foreign files,
  never touches project memory.

.EXAMPLE
  irm https://raw.githubusercontent.com/nirodg/session-guardian/main/install.ps1 -OutFile install.ps1; .\install.ps1
#>
[CmdletBinding()]
param(
  [ValidateSet("auto", "codex", "claude", "opencode", "generic", "none")]
  [string]$Agent = "auto",
  [string]$Version = $(if ($env:SESSION_GUARDIAN_VERSION) { $env:SESSION_GUARDIAN_VERSION } else { "main" }),
  [string]$Source = $env:SESSION_GUARDIAN_SOURCE,
  [switch]$Init,
  [switch]$Yes,
  [switch]$Uninstall,
  [switch]$AddToPath
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2

$RepoUrl = if ($env:SESSION_GUARDIAN_REPO) { $env:SESSION_GUARDIAN_REPO } else { "https://github.com/nirodg/session-guardian.git" }
$Root = if ($env:SESSION_GUARDIAN_HOME) { $env:SESSION_GUARDIAN_HOME } else { Join-Path $env:LOCALAPPDATA "Programs\session-guardian" }
$Bin = if ($env:SESSION_GUARDIAN_BIN) { $env:SESSION_GUARDIAN_BIN } else { Join-Path $Root "bin" }
$Marker = "REM SessionGuardian wrapper"
$Wrapper = Join-Path $Bin "session-guardian.cmd"
$ManifestPath = Join-Path $Root "install-manifest.json"

function Find-Python {
  foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    $exe = $candidate[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $extra = @($candidate | Select-Object -Skip 1)
    try {
      $path = & $exe @extra -c "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')" 2>$null
      if ($LASTEXITCODE -eq 0 -and $path) { return $path.Trim() }
    } catch { }
  }
  throw "Python 3.9+ is required (https://www.python.org/downloads/)."
}

function Get-Sha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

function Confirm-Step([string]$Question) {
  if ($Yes -or -not [Environment]::UserInteractive) { return $true }
  $reply = Read-Host "$Question [Y/n]"
  return ($reply -eq "" -or $reply -match "^[Yy]")
}

$Python = Find-Python

if ($Uninstall) {
  $core = Join-Path $Root "core\session_guardian.py"
  if (-not (Test-Path $core)) { throw "SessionGuardian is not installed in $Root." }
  & $Python $core uninstall --yes
  if ((Test-Path $Wrapper) -and (Select-String -LiteralPath $Wrapper -SimpleMatch $Marker -Quiet)) { Remove-Item -LiteralPath $Wrapper -Force }
  foreach ($d in @($Bin, $Root)) { if ((Test-Path $d) -and -not (Get-ChildItem -LiteralPath $d -Force)) { Remove-Item -LiteralPath $d -Force } }
  Write-Host "SessionGuardian uninstalled. Project memory (.session-guardian\) was not touched."
  return
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("sg-install-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  if ($Source) {
    $src = (Resolve-Path $Source).Path
  } elseif (Get-Command git -ErrorAction SilentlyContinue) {
    $src = Join-Path $tmp "repo"
    & git clone --quiet --depth 1 --branch $Version $RepoUrl $src 2>$null
    if ($LASTEXITCODE -ne 0) {
      Remove-Item -Recurse -Force $src -ErrorAction SilentlyContinue
      & git init --quiet $src; & git -C $src remote add origin $RepoUrl
      & git -C $src fetch --quiet --depth 1 origin $Version; if ($LASTEXITCODE -ne 0) { throw "Could not download SessionGuardian ($Version)." }
      & git -C $src checkout --quiet FETCH_HEAD
    }
  } else {
    $zip = Join-Path $tmp "src.zip"
    $base = $RepoUrl -replace "\.git$", ""
    Invoke-WebRequest -UseBasicParsing -Uri "$base/archive/$Version.zip" -OutFile $zip
    Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $tmp "zip")
    $src = (Get-ChildItem -Directory (Join-Path $tmp "zip") | Select-Object -First 1).FullName
  }
  foreach ($f in @("core\session_guardian.py", "skills\session-guardian\SKILL.md", "templates\SCOPE.md")) {
    if (-not (Test-Path (Join-Path $src $f))) { throw "Invalid package: $f missing." }
  }
  & $Python (Join-Path $src "core\session_guardian.py") doctor *> $null
  if ($LASTEXITCODE -ne 0) { throw "Invalid package: core does not run." }
  $versionText = & $Python (Join-Path $src "core\session_guardian.py") --version 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $versionText) { $versionText = "session-guardian $Version" }

  # Stage, then swap each component into place.
  New-Item -ItemType Directory -Force -Path $Root, $Bin | Out-Null
  $stage = Join-Path $Root ".install-staging"
  if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
  New-Item -ItemType Directory -Force -Path (Join-Path $stage "core"), (Join-Path $stage "skills\session-guardian"), (Join-Path $stage "templates") | Out-Null
  Copy-Item (Join-Path $src "core\session_guardian.py") (Join-Path $stage "core\")
  Copy-Item (Join-Path $src "skills\session-guardian\SKILL.md") (Join-Path $stage "skills\session-guardian\")
  Copy-Item (Join-Path $src "templates\*") (Join-Path $stage "templates\") -Recurse
  foreach ($component in @("core", "skills", "templates")) {
    $dest = Join-Path $Root $component
    $old = "$dest.old"
    if (Test-Path $old) { Remove-Item -Recurse -Force $old }
    if (Test-Path $dest) { Move-Item $dest $old }
    Move-Item (Join-Path $stage $component) $dest
    if (Test-Path $old) { Remove-Item -Recurse -Force $old }
  }
  Remove-Item -Recurse -Force $stage

  $binOk = $true
  if ((Test-Path $Wrapper) -and -not (Select-String -LiteralPath $Wrapper -SimpleMatch $Marker -Quiet)) {
    Write-Warning "Not overwriting $Wrapper: it was not created by SessionGuardian."
    $binOk = $false
  } else {
    $core = Join-Path $Root "core\session_guardian.py"
    Set-Content -LiteralPath $Wrapper -Encoding ASCII -Value "@echo off`r`n$Marker`r`n`"$Python`" `"$core`" %*"
  }

  # Skills: upgrade only copies that are unmodified since we installed them.
  $previous = @{}
  if (Test-Path $ManifestPath) {
    try { foreach ($s in (Get-Content -Raw $ManifestPath | ConvertFrom-Json).skills) { $previous[$s.path] = $s.sha256 } } catch { }
  }
  $newSkill = Join-Path $Root "skills\session-guardian\SKILL.md"
  $targets = @()
  $homeDir = $env:USERPROFILE
  $known = @{ codex = ".codex\skills"; claude = ".claude\skills"; opencode = ".config\opencode\skills"; generic = ".agents\skills" }
  if ($Agent -eq "auto") {
    foreach ($rel in @(".agents\skills", ".codex\skills", ".claude\skills", ".config\opencode\skills")) {
      $d = Join-Path $homeDir $rel
      if (Test-Path $d) { $targets += (Join-Path $d "session-guardian") }
    }
    if (-not $targets) { $targets += (Join-Path $homeDir ".agents\skills\session-guardian") }
  } elseif ($Agent -ne "none") {
    $targets += (Join-Path (Join-Path $homeDir $known[$Agent]) "session-guardian")
  }
  $installed = @{}
  foreach ($k in $previous.Keys) { if (Test-Path (Join-Path $k "SKILL.md")) { $installed[$k] = $previous[$k] } }
  if ($targets -and (Confirm-Step "Install the agent skill into: $($targets -join ', ')?")) {
    foreach ($t in $targets) {
      $file = Join-Path $t "SKILL.md"
      if (Test-Path $file) {
        $current = Get-Sha256 $file
        if ($current -eq (Get-Sha256 $newSkill)) { Write-Host "Skill up to date at $t" }
        elseif ($previous.ContainsKey($t) -and $previous[$t] -eq $current) { Copy-Item $newSkill $file -Force; Write-Host "Upgraded skill at $t" }
        else { Write-Host "Preserving existing skill at $file (modified or not installed by SessionGuardian)"; continue }
      } else {
        New-Item -ItemType Directory -Force -Path $t | Out-Null
        Copy-Item $newSkill $file
        Write-Host "Installed skill at $t"
      }
      $installed[$t] = Get-Sha256 $file
    }
  }

  $files = @((Join-Path $Root "core"), (Join-Path $Root "skills"), (Join-Path $Root "templates"))
  if ($binOk) { $files += $Wrapper }
  $manifest = [ordered]@{
    format_version = 1
    version = ($versionText -split " ")[-1]
    ref = $Version
    installed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss+00:00")
    root = $Root
    files = $files
    skills = @($installed.Keys | Sort-Object | ForEach-Object { [ordered]@{ path = $_; sha256 = $installed[$_] } })
  }
  $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$ManifestPath.tmp" -Encoding UTF8
  Move-Item -Force "$ManifestPath.tmp" $ManifestPath

  $doctor = & $Python (Join-Path $Root "core\session_guardian.py") doctor | Out-String
  if ($LASTEXITCODE -ne 0 -or -not ($doctor | ConvertFrom-Json).python_supported) { throw "Installation validation failed:`n$doctor" }

  Write-Host "$versionText installed in $Root."
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($binOk -and -not (($userPath -split ";") -contains $Bin)) {
    if ($AddToPath) {
      [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $Bin), "User")
      Write-Host "Added $Bin to your user PATH. Open a new terminal to use 'session-guardian'."
    } else {
      Write-Host "Add $Bin to PATH to use 'session-guardian' (re-run with -AddToPath to do it for you)."
    }
  }
  if ($Init) { & $Python (Join-Path $Root "core\session_guardian.py") init . }
  Write-Host "Next: cd into a project and run 'session-guardian init', then 'session-guardian integrate <agent>'."
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
