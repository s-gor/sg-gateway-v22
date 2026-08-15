$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& .\scripts\test.ps1

Write-Host 'Checking Python syntax...'
& .\.venv\Scripts\python.exe -B -c "from pathlib import Path; files=list(Path('app').rglob('*.py'))+list(Path('engines').rglob('*.py'))+list(Path('tests').rglob('*.py'))+list(Path('hostd').rglob('*.py')); [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in files]; print(f'syntax ok: {len(files)} files')"

Write-Host 'Checking release manifest...'
& .\.venv\Scripts\python.exe -B -c "import json, pathlib; manifest=json.loads(pathlib.Path('release-manifest.json').read_text(encoding='utf-8')); version=pathlib.Path('VERSION').read_text(encoding='utf-8').strip(); assert manifest['version']==version; assert manifest['images']['panel']; assert manifest['images']['xray']; print('manifest ok')"

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host 'Checking Docker Compose config...'
    docker compose config | Out-Null
} else {
    Write-Host 'Docker not found, skipping compose check.'
}

Write-Host 'Running hostd tests...'
& .\.venv\Scripts\python.exe -m pip install -r hostd/requirements.txt
$env:PYTHONPATH = 'hostd'
& .\.venv\Scripts\python.exe -m pytest hostd/tests

Write-Host 'Local CI checks completed.'
