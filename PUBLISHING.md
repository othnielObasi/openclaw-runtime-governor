Publishing packages (PyPI, npm & Maven Central)
=================================================

Required GitHub repository secrets
- `PYPI_API_TOKEN` – token for PyPI publish (used by `pypa/gh-action-pypi-publish`).
- `NPM_TOKEN` – npm auth token for `npm publish` (used by `actions/setup-node`).
- `OSSRH_USERNAME` / `OSSRH_PASSWORD` – Sonatype OSSRH credentials for Maven Central.
- `GPG_PRIVATE_KEY` / `GPG_PASSPHRASE` – GPG key for signing Maven artifacts.
- `CODECOV_TOKEN` (optional) – token to upload coverage reports to Codecov.

Release flow (recommended)
1. Create a GitHub release (draft or published) on `main`.
2. The `.github/workflows/publish-python.yml`, `.github/workflows/publish-js.yml`, and `.github/workflows/publish-java.yml` workflows will run on release and publish the packages automatically using the above secrets.

---

Manual publish (Python — PyPI)
```bash
cd openclaw-skills/governed-tools
python -m build
python -m twine upload dist/* -u __token__ -p "$PYPI_API_TOKEN"
```

Package name: `openclaw-governor-client`

---

Manual publish (TypeScript/JS — npm)
```bash
cd openclaw-skills/governed-tools/js-client
npm run build          # produces dual CJS + ESM output
# ensure NODE_AUTH_TOKEN is set (or use npm login)
NODE_AUTH_TOKEN="$NPM_TOKEN" npm publish --access public
```

Package name: `@openclaw/governor-client`
Build output: `dist/cjs/` (CommonJS) + `dist/esm/` (ES Modules)

---

Manual publish (Java — Maven Central)
```bash
cd openclaw-skills/governed-tools/java-client

# Build, test, and deploy to Maven Central via Sonatype OSSRH
mvn clean deploy -P release \
  -Dgpg.passphrase="$GPG_PASSPHRASE"
```

Package coordinates: `dev.openclaw:governor-client:0.2.0`
Requires: Java 11+, Maven 3.8+, GPG key registered with Sonatype

---

Notes and checklist
- Ensure `pyproject.toml` has correct metadata (name, version, authors, readme).
- Ensure `package.json` for JS package includes `repository` and `files` to publish only built artefacts.
- Ensure `pom.xml` has correct `<groupId>`, `<artifactId>`, `<version>`, and `<developers>` tags.
- Verify `npm run build` produces both `dist/cjs/` and `dist/esm/` directories.
- Verify `mvn test` passes all 6 Java tests before publishing.
- Do NOT commit `node_modules/`, build outputs, or platform-specific native binaries. Use `.gitignore` and CI builds instead.
- If large binary files accidentally committed (e.g. Next SWC), remove them from history with `git filter-repo` or BFG before pushing to `main`.
