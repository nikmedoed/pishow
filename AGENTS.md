# Agent Instructions

## Python environment

Use the project virtual environment for Python commands. Do not probe or install system-level Python dependencies first.

On Windows/PowerShell, prefer:

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py src
.\.venv\Scripts\python.exe -c "import main; print('import ok')"
.\.venv\Scripts\python.exe -m pytest -q
```

If a package is missing in `.venv`, report that the project virtual environment is missing the dependency. Do not treat the system Python result as authoritative for this project.

