Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

& ".\.venv\Scripts\python.exe" -m streamlit run app.py `
    --server.port 8501 `
    --server.address 127.0.0.1 `
    --server.headless true `
    --browser.gatherUsageStats false
