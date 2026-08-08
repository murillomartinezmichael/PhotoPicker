# PUBLISHING — releasing photopicker to PyPI

Package is build-verified and ready. This is the exact sequence for Michael to run
once he has a PyPI account + API token (account/token creation is a manual gate —
agents don't own accounts or credentials).

## One-time setup

1. Create a PyPI account: https://pypi.org/account/register/
2. (Recommended) Also create a TestPyPI account for a dry run first: https://test.pypi.org/account/register/
3. Enable 2FA on both (PyPI requires it for new accounts).
4. Generate an API token:
   - PyPI: https://pypi.org/manage/account/token/ — scope it to the `photopicker` project after the first upload (project-scoped tokens can't be created until the project exists, so the very first upload has to use an account-wide token; narrow it to project-scoped immediately after).
   - TestPyPI: https://test.pypi.org/manage/account/token/
5. Store the token somewhere `twine` can read it — either:
   - `~/.pypirc` (see template below), or
   - paste it interactively when `twine upload` prompts (username `__token__`, password = the token, including the `pypi-` prefix).

`~/.pypirc` template:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-...your-real-token...

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-...your-testpypi-token...
```

Keep this file out of git (it already lives outside the repo at `~`, so no gitignore entry is needed).

## Every release

From the repo root, with the project venv active:

```bash
# 1. Bump version in pyproject.toml (single source of truth — no other file to sync)
#    Current: 0.14.0

# 2. Clean old build artifacts (dist/, build/, *.egg-info/ are gitignored, safe to remove)
rm -rf dist build photopicker.egg-info

# 3. Install/upgrade the build + upload tooling (one-time, or when stale)
python -m pip install --upgrade build twine

# 4. Build the sdist + wheel
python -m build

# 5. Sanity-check the artifacts before uploading anywhere
twine check dist/*
```

### Recommended: dry run on TestPyPI first

```bash
twine upload -r testpypi dist/*
# Then verify the install actually works from TestPyPI in a scratch venv:
python -m venv /tmp/pp_test_install
source /tmp/pp_test_install/Scripts/activate   # Windows Git Bash
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ photopicker
python -c "import photopicker; print(photopicker.pick_photos)"
```

The `--extra-index-url` is required because TestPyPI doesn't mirror real dependencies
(pillow, opencv, etc.) — without it, pip can't resolve photopicker's own deps.

### Real upload

```bash
twine upload dist/*
```

Confirm at https://pypi.org/project/photopicker/ — then:

```bash
pip install photopicker
python -c "import photopicker; print(photopicker.pick_photos)"
```

## After the first successful publish

- Flip README.md's "Install" section from the "not on PyPI yet, clone-based install"
  block to `pip install photopicker` (+ `pip install "photopicker[vision]"` etc. for extras).
- Narrow the PyPI API token from account-wide to project-scoped
  (https://pypi.org/manage/account/token/ → scope to `photopicker`), then update `~/.pypirc`.
- Check off the PENDING_MANUAL.md publish item.

## Version bump checklist (every release after the first)

1. Bump `version` in `pyproject.toml`.
2. Add a `CHANGELOG.md` entry.
3. Run the full test suite green (`pytest`).
4. Follow "Every release" above.
5. `git tag vX.Y.Z && git push origin vX.Y.Z` (optional but recommended — lets GitHub releases line up with PyPI versions).
