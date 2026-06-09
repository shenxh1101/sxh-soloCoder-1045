@echo off
setlocal
set "PYTHONPATH=%~dp0src"
set "PYTHONIOENCODING=utf-8"
set "EFFCLI_DB_PATH=%~dp0.effcli\effcli.db"
python -m effcli.cli %*
endlocal
