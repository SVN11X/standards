# scripts

- `standard.py`: the engine of the standard. Run `python scripts/standard.py --help` for the commands. Needs PyYAML (`pip install pyyaml`).
- `publish-templates.sh` (bash) and `publish-templates.ps1` (Windows PowerShell): build one template repository per profile and push them to GitHub as template repositories. They need Python with PyYAML and the GitHub CLI (`gh`), logged in.
- On Windows, run the PowerShell version with `powershell -ExecutionPolicy Bypass -File .\scripts\publish-templates.ps1`, because Windows blocks unsigned scripts by default.
