# RoleHawk installer for Windows (PowerShell 5.1 or later).
#
#   irm https://raw.githubusercontent.com/travist6983/rolehawk/main/scripts/install.ps1 | iex
#
# Everything goes in your user profile; nothing needs admin rights:
#   %USERPROFILE%\.local\bin\uv.exe          uv, if you don't have it (it brings Python 3.12)
#   %USERPROFILE%\.rolehawk\               the app (one folder per version) and Chromium (~150 MB)
#   %USERPROFILE%\.local\bin\rolehawk.cmd  the `rolehawk` command
#   Desktop and Start menu shortcuts         "RoleHawk"
# Your data lives in %USERPROFILE%\RoleHawk; reinstalling or updating never touches it.
#
# Optional settings: ROLEHAWK_APP_HOME (install folder), ROLEHAWK_BIN_DIR (where the
# `rolehawk` command goes), ROLEHAWK_RELEASE_URL (where the release files come from),
# ROLEHAWK_NO_START=1 (don't start the app at the end), ROLEHAWK_NO_SHORTCUT=1.
#
# Everything is inside Install-RoleHawk, called on the last lines, so a partial download
# runs nothing. It never calls `exit` (that would close your PowerShell window).

function Install-RoleHawk {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"  # the progress bar makes downloads very slow
    $UvVersion = "0.10.7"
    $Releases = "https://github.com/travist6983/rolehawk/releases/latest/download"

    function Say([string]$Text) { Write-Host $Text -ForegroundColor Cyan }

    function Invoke-Native([string]$What, [scriptblock]$Command) {
        & $Command
        if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
    }

    function Find-Uv {
        $found = Get-Command uv -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
        foreach ($dir in @($env:XDG_BIN_HOME, (Join-Path $env:USERPROFILE ".local\bin"))) {
            if ($dir -and (Test-Path (Join-Path $dir "uv.exe"))) { return (Join-Path $dir "uv.exe") }
        }
        return $null
    }

    # Windows PowerShell 5.1 may not offer TLS 1.2 by default.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $AppHome = if ($env:ROLEHAWK_APP_HOME) { $env:ROLEHAWK_APP_HOME } else { Join-Path $env:USERPROFILE ".rolehawk" }
    $Base = if ($env:ROLEHAWK_RELEASE_URL) { $env:ROLEHAWK_RELEASE_URL } else { $Releases }
    $Base = $Base.TrimEnd("/")
    $DataHome = if ($env:ROLEHAWK_HOME) { $env:ROLEHAWK_HOME } else { Join-Path $env:USERPROFILE "RoleHawk" }

    Say "RoleHawk installer (Windows, $env:PROCESSOR_ARCHITECTURE)"
    Write-Host "This installs, in your user profile only (no admin rights needed):"
    Write-Host "  - uv, which manages Python 3.12 for the app (if it isn't installed yet)"
    Write-Host "  - RoleHawk into $AppHome, including Chromium for PDFs and autofill (about 150 MB)"
    Write-Host "  - the 'rolehawk' command and Desktop and Start menu shortcuts"
    Write-Host "Your data will live in $DataHome."
    Write-Host ""

    $uv = Find-Uv
    if (-not $uv) {
        Say "Installing uv $UvVersion..."
        # A separate process, so anything the uv installer does can't close this window.
        $shell = (Get-Process -Id $PID).Path
        Invoke-Native "Installing uv" {
            & $shell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/$UvVersion/install.ps1 | iex"
        }
        $uv = Find-Uv
        if (-not $uv) { throw "uv didn't install. See https://docs.astral.sh/uv/ and try again." }
    }
    Write-Host "Using uv at $uv"

    # Unpack inside the install folder so the final move stays on one drive.
    $versions = Join-Path $AppHome "versions"
    $downloads = Join-Path $AppHome "downloads"
    New-Item -ItemType Directory -Force $versions, $downloads | Out-Null
    $tmp = Join-Path $downloads ("install-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory $tmp | Out-Null
    try {
        Say "Downloading the latest release..."
        $zip = Join-Path $tmp "rolehawk.zip"
        Invoke-WebRequest -UseBasicParsing "$Base/rolehawk.zip" -OutFile $zip
        Invoke-WebRequest -UseBasicParsing "$Base/rolehawk.zip.sha256" -OutFile "$zip.sha256"
        $expected = ((Get-Content "$zip.sha256" -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
        $actual = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLowerInvariant()
        if ($expected -ne $actual) { throw "The download doesn't match its checksum. Try again." }

        # Python's zipfile (through uv) unpacks it: it drops absolute paths and '..' from
        # member names, and never creates links.
        $unpackTo = Join-Path $tmp "x"
        Invoke-Native "Unpacking" { & $uv run --quiet --no-project --python 3.12 python -m zipfile -e $zip $unpackTo }
        $unpacked = @(Get-ChildItem -Directory $unpackTo -Filter "rolehawk-*")
        if ($unpacked.Count -ne 1 -or -not (Test-Path (Join-Path $unpacked[0].FullName "VERSION"))) {
            throw "The release has an unexpected layout."
        }
        $version = (Get-Content (Join-Path $unpacked[0].FullName "VERSION") -Raw).Trim()
        if ($version -notmatch '^\d{1,4}\.\d{1,4}\.\d{1,4}$') { throw "Bad release version." }

        $app = Join-Path $versions $version
        if (Test-Path $app) {
            Write-Host "Reinstalling version $version."
            Remove-Item -Recurse -Force $app
        }
        Move-Item $unpacked[0].FullName $app

        Say "Installing RoleHawk $version (Python 3.12 and packages)..."
        Push-Location (Join-Path $app "backend")
        try {
            Invoke-Native "Installing packages" { & $uv sync --quiet --frozen --no-dev --python 3.12 }
        } finally {
            Pop-Location
        }
        $exe = Join-Path $app "backend\.venv\Scripts\rolehawk.exe"

        Say "Installing Chromium (PDF export and autofill)..."
        Invoke-Native "Installing Chromium" { & $exe install-browser }

        $pointer = Join-Path $AppHome "current"
        Set-Content -Path "$pointer.partial" -Value $version -NoNewline -Encoding Ascii
        Move-Item -Force "$pointer.partial" $pointer

        Say "Setting up your data folder..."
        Invoke-Native "Setting up the data folder" { & $exe db upgrade }

        $uvBin = (& $uv tool dir --bin).Trim()
        $binDir = if ($env:ROLEHAWK_BIN_DIR) { $env:ROLEHAWK_BIN_DIR } else { $uvBin }
        New-Item -ItemType Directory -Force $binDir | Out-Null
        # %USERPROFILE% stays a variable, so the launcher works whatever characters are in the
        # user name (cmd.exe reads .cmd files in the console code page, not UTF-8).
        $homeRef = if ($env:ROLEHAWK_APP_HOME) { $AppHome } else { "%USERPROFILE%\.rolehawk" }
        $launcher = Join-Path $binDir "rolehawk.cmd"
        Set-Content -Path $launcher -Encoding Ascii -Value @(
            "@echo off",
            "rem RoleHawk launcher, written by the installer. Runs the version named in ""current"";",
            "rem ``rolehawk update`` installs new versions next to it and moves that pointer.",
            "setlocal",
            "set /p ROLEHAWK_VERSION=<""$homeRef\current""",
            """$homeRef\versions\%ROLEHAWK_VERSION%\backend\.venv\Scripts\rolehawk.exe"" %*",
            "exit /b %ERRORLEVEL%"
        )

        $pathNote = $null
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $onPath = @($userPath -split ";") -contains $binDir
        if (-not $onPath) {
            if ($binDir -eq $uvBin) {
                Invoke-Native "Adding the command to PATH" { & $uv tool update-shell *> $null }
                $pathNote = "Open a new terminal window for the 'rolehawk' command to work."
            } else {
                $pathNote = "Add $binDir to your PATH to use the 'rolehawk' command."
            }
        }
        $env:Path = "$binDir;$env:Path"

        if ($env:ROLEHAWK_NO_SHORTCUT -ne "1") {
            $wsh = New-Object -ComObject WScript.Shell
            $places = @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))
            foreach ($place in $places) {
                if (-not $place -or -not (Test-Path $place)) { continue }
                $link = $wsh.CreateShortcut((Join-Path $place "RoleHawk.lnk"))
                $link.TargetPath = $launcher
                $link.Arguments = "start"
                $link.WorkingDirectory = $env:USERPROFILE
                $link.Description = "RoleHawk job search copilot"
                $link.Save()
            }
        }
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Say "RoleHawk $version is installed."
    Write-Host "Start it any time with 'rolehawk' or the RoleHawk shortcut on your Desktop."
    Write-Host "Update with 'rolehawk update'. Diagnostics: 'rolehawk doctor'."
    if ($pathNote) { Write-Host $pathNote }
    if ($env:ROLEHAWK_NO_START -ne "1") {
        Write-Host ""
        Say "Starting RoleHawk (press Ctrl+C to stop)..."
        & $exe start
    }
}

try {
    Install-RoleHawk
} catch {
    Write-Host "RoleHawk install failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Your data folder is untouched. Run the install line again to retry, or see the README's troubleshooting section."
    # Run as a file (CI, or `powershell -File`): report failure. Piped into iex: keep the window.
    if ($PSCommandPath) { exit 1 }
}
