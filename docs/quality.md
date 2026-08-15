# Quality checks

Before publishing changes:

```powershell
.\scripts\ci-local.ps1
```

or on Linux:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
bash -n install.sh
bash -n build-run.sh
```

The repository also checks:

- Python syntax;
- JSON manifests;
- Jinja templates;
- the clean SQLite seed and AmneziaWG UDP 585 invariant;
- self-contained installer payload verification.
