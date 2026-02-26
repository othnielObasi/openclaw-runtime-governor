Publishing packages (PyPI & npm)
================================

Required GitHub repository secrets
- `PYPI_API_TOKEN` – token for PyPI publish (used by `pypa/gh-action-pypi-publish`).
- `NPM_TOKEN` – npm auth token for `npm publish` (used by `actions/setup-node`).
- `CODECOV_TOKEN` (optional) – token to upload coverage reports to Codecov.

Release flow (recommended)
1. Create a GitHub release (draft or published) on the `feat/client-sdks-clean` branch.
2. The `.github/workflows/publish-python.yml` and `.github/workflows/publish-js.yml` workflows will run on release and publish the packages automatically using the above secrets.

Manual publish (Python)
```bash
cd openclaw-skills/governed-tools
python -m build
python -m twine upload dist/* -u __token__ -p "$PYPI_API_TOKEN"
```

Manual publish (npm)
```bash
cd openclaw-skills/governed-tools/js-client
# ensure NODE_AUTH_TOKEN is set (or use npm login)
NODE_AUTH_TOKEN="$NPM_TOKEN" npm publish --access public
```

Notes and checklist
- Ensure `pyproject.toml` has correct metadata (name, version, authors, readme).
- Ensure `package.json` for JS package includes `repository` and `files` to publish only built artefacts.
- Do NOT commit `node_modules/`, build outputs, or platform-specific native binaries. Use `.gitignore` and CI builds instead.
- If large binary files accidentally committed (e.g. Next SWC), remove them from history with `git filter-repo` or BFG before pushing to `main`.
