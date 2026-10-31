$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Definition)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.10 or newer is required."
    exit 1
}

python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
