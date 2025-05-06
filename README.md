# Package Statistics

A Python command-line tool that downloads and parses Debian `Contents-<arch>.gz` indices and reports the top-N packages by file count.

## Overview

`package_statistics.py` is a Python CLI tool that:

- Downloads the Debian `Contents-<arch>.gz` index for a specified architecture.
- Parses each line by splitting on the last run of whitespace to extract package names.
- Counts how many files each package contains.
- Displays the results in a neat table sorted by file count.

It includes logging, error handling for download failures, and clean exit on broken pipes (e.g., when piping to `head`).

## Features

- **CLI options** for architecture, mirror URL, distribution, component, number of top packages, and verbose logging.
- **Robust parsing** handles file paths with spaces and skips malformed or header lines.
- **Graceful error handling** for HTTP/URL errors during download and malformed input.
- **Tabular output** with configurable column widths and TTY warning for large output.
- **Broken-pipe support** to exit cleanly when downstream commands close the pipe.
- **Type-annotated code** (Python 3.10+), checked by `mypy`.
- **Pre-commit style enforcement** via `black` (formatting) and `ruff` (linting and import sorting).
- **Makefile targets** for development tasks (formatting, linting, testing).

## Installation

1. Clone the repo:

   ```bash
   git clone https://github.com/dmdaksh/deb-pkg-stats.git
   cd deb-pkg-stats
   ```

2. (Optional) Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install development dependencies (includes testing and linting tools):

   ```bash
   pip install -r requirements-dev.txt
   # or
   make install
   ```

## Usage

Make the script executable and run:

```bash
chmod +x src/package_statistics.py
./src/package_statistics.py <arch> [options]
```

### Examples

- Top 10 packages for `amd64`:

  ```bash
  ./src/package_statistics.py amd64
  ```

- Top 5 packages for `arm64` on a custom mirror:

  ```bash
  ./src/package_statistics.py arm64 --top 5 \
      --mirror <http://deb.debian.org/debian> --verbose
  ```

### CLI Options

| Flag            | Default                           | Description                    |
| --------------- | --------------------------------- | ------------------------------ |
| `--mirror`      | `http://ftp.uk.debian.org/debian` | Base Debian mirror URL         |
| `--dist`        | `stable`                          | Distribution name              |
| `--component`   | `main`                            | Repository component           |
| `--top`         | `10`                              | Number of top packages to show |
| `--verbose, -v` | `off`                             | Enable debug logging           |

## Testing

This project uses `pytest` with coverage reporting.

To run the tests:

```bash
make test
# or
pytest
```

To check type, lint, and tests together:

```bash
make check
```

To view coverage report:

```bash
pytest --cov=package_statistics --cov-report term-missing
```

## Design & Implementation

1. `download_contents`: retrieves and validates the gzipped index via `urllib`.

2. `parse_contents`: iterates lines, uses `rsplit` to split on the last whitespace run, strips prefixes, yields package names.

3. `get_top_packages`: orchestrates download, parsing, and counting in a reusable function.

4. `main`: CLI entrypoint with `argparse`, logging config, error handling, and tabular output formatting.

## Notes on Contents File Format

While the [Debian Wiki documentation](https://wiki.debian.org/RepositoryFormat#A.22Contents.22_indices) suggests that Contents index files _may_ start with a header line (`FILE LOCATION`), practical checks against the default mirror (`http://ftp.uk.debian.org/debian/dists/stable/main/`) for various architectures (like `amd64`, `arm64`) showed that the files begin directly with the file-to-package mapping data.

The parser in this script (`parse_contents`) is implemented to handle this observed format correctly by processing lines from the start, assuming each valid line contains a file path followed by package names.

## Development

This project includes a `Makefile` to streamline common tasks:

- `make install` - Install development dependencies (`requirements-dev.txt`).
- `make format` - Format code (`black`) and fix imports/style (`ruff --fix`).
- `make lint` - Lint code using `ruff`.
- `make typecheck` - Static type check with `mypy`.
- `make test` - Run tests with `pytest`.
- `make check` - Run lint, typecheck, and tests.
- `make all` - Run `make format` and `make check` (default).
- `make clean` - Remove caches, coverage artifacts, and generated files.

## Configuration (pyproject.toml)

Tool configuration is centralized in `pyproject.toml`:

- **Black**: `line-length = 88`, `target-version = ['py310']`
- **Ruff**: `line-length = 88`, rules under `[tool.ruff.lint]`, ignores E501
- **isort**: `profile = 'black'`, first-party imports recognized
- **MyPy**: Python 3.10, `disallow_untyped_defs = true`, `ignore_missing_imports = true`
- **pytest**: `addopts = '-rA -q --cov=package_statistics --cov-report term-missing'`, `testpaths = ['tests']`
- **.gitignore**: Excludes Python caches, coverage reports, virtual environments, OS files, and LaTeX auxiliary outputs.

## Time Log

| Task                                   | Time Spent |
| -------------------------------------- | ---------- |
| Requirements analysis                  | 0h 20m     |
| Initial implementation                 | 0h 45m     |
| Parsing refinement                     | 0h 20m     |
| CLI, error handling & pipe support     | 0h 30m     |
| Unit tests development (all cases)     | 2h 15m     |
| Test coverage improvements             | 0h 20m     |
| Documentation updates (README, report) | 0h 30m     |
| Makefile & .gitignore enhancements     | 0h 15m     |
| Tabular output formatting              | 0h 25m     |
| Final debugging & cleanup              | 0h 20m     |
| **Total**                              | **6h**     |
