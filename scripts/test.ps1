$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-SystemPython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return 'py -3'
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return 'python'
    }
    throw 'Python was not found. Install Python 3 and try again.'
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)][string]$PythonCommand,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    if ($PythonCommand -eq 'py -3') {
        & py -3 @Arguments
    } else {
        & $PythonCommand @Arguments
    }
}

$VenvPython = '.\.venv\Scripts\python.exe'

if (Test-Path $VenvPython) {
    & $VenvPython --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Existing .venv is not runnable. Recreate .venv manually if this keeps failing.'
        exit 1
    }
} else {
    $SystemPython = Get-SystemPython
    Invoke-Python $SystemPython -m venv .venv
}

& $VenvPython -m pip install -r requirements-dev.txt
& $VenvPython -m pytest tests
