[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $PytestArgs
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot "venv\Scripts\python.exe"
$Selection = "not live and not model and not gpu"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Phase 3 verification requires $Python"
}

$HadPreviousValue = Test-Path Env:\PHASE3_NO_SKIPS
$PreviousValue = $env:PHASE3_NO_SKIPS
$ExitCode = 1

try {
    $env:PHASE3_NO_SKIPS = "1"
    & $Python -m pytest @PytestArgs -m $Selection --disable-socket
    $ExitCode = $LASTEXITCODE
}
finally {
    if ($HadPreviousValue) {
        $env:PHASE3_NO_SKIPS = $PreviousValue
    }
    else {
        Remove-Item Env:\PHASE3_NO_SKIPS -ErrorAction SilentlyContinue
    }
}

exit $ExitCode
