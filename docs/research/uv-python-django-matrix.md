# Testing Python and Django versions with uv

Research date: 2026-10-28

## Finding

This command is technically valid:

```yaml
uv add --group tests --python ${{ matrix.python }} "Django==${{ matrix.django }}.*; python_version == '${{ matrix.python }}'"
```

The Python marker limits the Django pin to the matrix Python version, avoiding a universal Django 6 pin that cannot resolve for Python 3.11. However, this is not the first-party documented CI pattern: `uv add` changes project dependency metadata and the lockfile on each CI run.

uv's GitHub Actions guide instead shows selecting Python through `setup-uv`, syncing the project, and running tests with `uv run`. To test alternate Django versions per matrix row without modifying project metadata, use uv's documented `--with` option:

```yaml
- uses: astral-sh/setup-uv@v6
  with:
    python-version: ${{ matrix.python }}

- run: uv sync --locked --group tests

- run: uv run --locked --group tests --with "Django==${{ matrix.django }}.*" pytest
```

This is an application of the documented CI and `uv run --with` patterns, not a Django-specific recipe published verbatim by uv.

## Why the marker works

`python_version == '3.11'` is a PEP 508 environment marker. It makes that dependency requirement apply only when the environment's Python version matches. The marker does not select the GitHub Actions matrix entry or install Python; the matrix selects the job and uv's `--python` or `setup-uv` configuration selects the interpreter.

The marker is necessary for the `uv add` approach because the project's `requires-python = ">=3.11"` includes Python 3.11, while Django 6 requires Python 3.12 or newer. An unmarked `Django==6.0.*` requirement therefore cannot resolve for the whole declared Python range. The marker makes the matrix-specific pin conditional instead.

## `requires-python`

Keep the project's `requires-python` declaration in `pyproject.toml`. It defines the package's supported Python range; it is not the CI matrix's interpreter selector. Change it only if the project's actual support policy changes.

## Sources

- [uv: GitHub Actions integration](https://docs.astral.sh/uv/guides/integration/github/), including [multiple Python versions](https://docs.astral.sh/uv/guides/integration/github/#multiple-python-versions)
- [uv: project dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/), including [platform-specific dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/#platform-specific-dependencies)
- [uv: running commands in projects](https://docs.astral.sh/uv/concepts/projects/run/), including per-invocation dependencies with `--with`
- [uv: project synchronization](https://docs.astral.sh/uv/concepts/projects/sync/), including `--locked`
- [uv: Python version requirement](https://docs.astral.sh/uv/concepts/projects/config/#python-version-requirement)
- [GitHub Actions: matrix strategies](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations)
- [Django 5.2 installation FAQ](https://docs.djangoproject.com/en/5.2/faq/install/)
- [Django 6.0 installation FAQ](https://docs.djangoproject.com/en/6.0/faq/install/)
- Project configuration: [`pyproject.toml`](../../pyproject.toml); current CI matrix: [`.github/workflows/tests.yaml`](../../.github/workflows/tests.yaml)
