# PowerShell one-time setup for reel-effects on Windows
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Write-Output "NEED_FFMPEG: install ffmpeg first (Windows: winget install ffmpeg)"
    exit 1
}

if (Test-Path ".venv\Scripts\python.exe") {
    & ".venv\Scripts\python.exe" -c "import mediapipe, cv2, PIL, numpy" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Output "READY"
        exit 0
    }
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv venv -q -p 3.12 .venv
    uv pip install -q -p ".venv\Scripts\python.exe" -r requirements.txt
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
} else {
    Write-Output "NEED_PYTHON: install Python 3.10 or newer, then run this again"
    exit 1
}

& ".venv\Scripts\python.exe" -c "import mediapipe, cv2, PIL, numpy; print('READY')"
