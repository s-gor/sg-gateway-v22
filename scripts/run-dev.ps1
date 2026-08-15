$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path '.venv')) {
    py -3 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

$env:SG_GATEWAY_ENV = 'development'
$env:SG_GATEWAY_HOST = '127.0.0.1'
$env:SG_GATEWAY_PORT = '8080'
$env:SG_GATEWAY_DATA_DIR = 'data'
$env:SG_GATEWAY_LOG_DIR = 'logs'

Write-Host 'SG-Gateway is starting at http://127.0.0.1:8080'
& .\.venv\Scripts\waitress-serve.exe --host=127.0.0.1 --port=8080 app.main:app