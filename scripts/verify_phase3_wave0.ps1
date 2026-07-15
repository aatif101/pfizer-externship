[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Wrapper = Join-Path $PSScriptRoot "run_phase3_pytest.ps1"

& $Wrapper `
    tests\test_phase3_dependency_contract.py `
    tests\test_import_contracts.py `
    -q

exit $LASTEXITCODE
