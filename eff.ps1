$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
$env:PYTHONIOENCODING = "utf-8"
$effDir = Join-Path $PSScriptRoot ".effcli"
$dbPath = Join-Path $effDir "effcli.db"
$env:EFFCLI_DB_PATH = $dbPath

python -m effcli.cli @args
