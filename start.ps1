param([int]$Port = 8526)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
python app.py --port $Port
exit $LASTEXITCODE
