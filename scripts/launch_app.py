from __future__ import annotations

import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

command = (
    f'cd /d "{ROOT}" && "{PYTHON}" -m streamlit run app.py '
    "--server.port 8501 "
    "--server.address 127.0.0.1 "
    "--server.headless true "
    "--browser.gatherUsageStats false"
)

process = subprocess.Popen(
    ["cmd.exe", "/k", command],
    cwd=ROOT,
    creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
)
print(process.pid)
