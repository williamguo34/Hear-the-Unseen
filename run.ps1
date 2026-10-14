# Face + Pose Landmarker + Arduino IMU saber. Windows entry, same job as run.zsh.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw 'Python 3 is not on PATH. Install it from python.org and include the py launcher.'
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "Missing $python. Delete .venv and run this script again."
}

& $python -c 'import aiohttp, cv2, numpy, mediapipe, pythonosc' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -r python-backend/tracker/requirements-face.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($args -notcontains '--iphone') {
    & $python -c 'import serial' 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $python -m pip install -r python-backend/tracker/requirements-imu.txt
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
if (-not (Test-Path phone/touchosc/HearTheUnseen.tosc)) {
    & $python phone/generate_touchosc.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Fetch-Model([string]$Dest, [string]$Url, [string]$Sha) {
    if (Test-Path $Dest) {
        if ((Get-Sha256 $Dest) -eq $Sha) { return }
        Write-Host "Checksum mismatch for $Dest; re-downloading…"
        Remove-Item $Dest -Force
    }
    Write-Host "Downloading $Dest…"
    $tmp = "$Dest.tmp"
    & curl.exe --fail --location --retry 3 --output $tmp $Url
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ((Get-Sha256 $tmp) -ne $Sha) {
        Remove-Item $tmp -Force
        throw "checksum failed for $Dest"
    }
    Move-Item $tmp $Dest -Force
}

Fetch-Model `
    'assets/face_landmarker.task' `
    'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task' `
    '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'

Fetch-Model `
    'assets/pose_landmarker_lite.task' `
    'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task' `
    '59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a'

$pythonRoot = Join-Path $PSScriptRoot 'python-backend'
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$pythonRoot;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $pythonRoot
}
& $python -m tracker.server @args
exit $LASTEXITCODE
