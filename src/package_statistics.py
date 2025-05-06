#!/usr/bin/env python3
"""
package_statistics.py

Download and parse Debian Contents-<arch>.gz, then report the top-N
packages by file-count. Follows PEP8, uses type hints, and includes
logging and configurable options.
"""

from __future__ import annotations

import argparse
import gzip
import logging
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from io import BytesIO, TextIOWrapper
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

# Default repository settings
DEFAULT_MIRROR: str = "http://ftp.uk.debian.org/debian"
DEFAULT_DIST: str = "stable"
DEFAULT_COMPONENT: str = "main"

# Configure module logger
logger = logging.getLogger(__name__)


def build_contents_url(
    arch: str,
    mirror: str,
    dist: str,
    comp: str,
) -> str:
    """
    Construct the Contents-<arch>.gz URL.
    """
    return f"{mirror}/dists/{dist}/{comp}/Contents-{arch}.gz"


def download_contents(
    arch: str,
    mirror: str,
    dist: str,
    comp: str,
) -> BytesIO:
    """
    Fetch and return the raw BytesIO of the Contents-<arch>.gz file.
    Raises HTTPError or URLError on failure.
    """
    url = build_contents_url(arch, mirror, dist, comp)
    logger.debug("Downloading Debian index from %s", url)
    try:
        # Ensure response is closed even if read() fails partially
        with urlopen(url) as response:
            if response.status != 200:
                error_msg = f"Download failed: Unexpected HTTP status {response.status} for {url}"
                logger.error(error_msg)
                # Use response.headers (HTTPMessage) to satisfy HTTPError typing
                raise HTTPError(
                    url, response.status, error_msg, hdrs=response.headers, fp=response
                )
            # Read entire response body
            content = response.read()

    except (HTTPError, URLError) as e:
        logger.error("Failed to download %s: %s", url, e)
        raise
    return BytesIO(content)


def parse_contents(stream: TextIOWrapper) -> Iterator[str]:
    """
    Yield each package name from a Debian Contents-<arch>.gz stream.
    Splits on the last run of whitespace to separate path and pkg-list.
    """
    for raw_line in stream:
        line = raw_line.strip()  # Strip leading/trailing whitespace from the whole line
        if not line:  # Skip empty lines after stripping
            continue

        # Explicitly skip header line based on common format
        # Note: This assumes the header starts with "FILE" and "LOCATION"
        # separated by whitespace. A more complex header might need adjustment.
        if line.startswith("FILE") and "LOCATION" in line.split(None, 2):
            logger.debug("Skipping header line: %r", raw_line)
            continue

        # Split on the *last* run of whitespace
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            # Skip malformed lines (no space delimiter found)
            logger.debug("Skipping malformed line (no space delimiter): %r", raw_line)
            continue

        _path_part, pkg_list_str = parts  # Unpack path and package list string

        # Process the package list string
        for pkg_raw in pkg_list_str.split(","):
            pkg_name_part = (
                pkg_raw.strip()
            )  # Strip whitespace around comma-separated items
            if pkg_name_part:  # Ensure it's not empty after stripping
                # Extract base name (part after the last '/')
                yield pkg_name_part.rsplit("/", 1)[-1]


def get_top_packages(
    arch: str,
    top_n: int,
    mirror: str = DEFAULT_MIRROR,
    dist: str = DEFAULT_DIST,
    comp: str = DEFAULT_COMPONENT,
) -> Sequence[tuple[str, int]]:
    """
    Download, parse, and return the top-N packages by file count.
    """
    bio = download_contents(arch, mirror, dist, comp)
    with gzip.GzipFile(fileobj=bio) as gz:
        text_stream = TextIOWrapper(gz, encoding="utf-8", errors="ignore")
        counts = Counter(parse_contents(text_stream))
    return counts.most_common(top_n)


def main() -> None:
    """
    Parse CLI arguments, compute top packages, and print results in a table.
    """
    parser = argparse.ArgumentParser(
        description=("Show top-N Debian packages by file-count in the Contents index.")
    )
    parser.add_argument("arch", help="Architecture (e.g., amd64, arm64, mips, ...)")
    parser.add_argument(
        "--mirror", default=DEFAULT_MIRROR, help="Base Debian mirror URL"
    )
    parser.add_argument(
        "--dist", default=DEFAULT_DIST, help="Distribution name (default: stable)"
    )
    parser.add_argument(
        "--component",
        default=DEFAULT_COMPONENT,
        help="Repository component (default: main)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top packages to display (default: 10)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        top_packages = get_top_packages(
            arch=args.arch,
            top_n=args.top,
            mirror=args.mirror,
            dist=args.dist,
            comp=args.component,
        )
    except Exception as e:  # Catch specific exceptions if possible, log error
        logger.exception(
            "An unexpected error occurred: %s", e  # Log the exception info
        )
        sys.exit(1)

    if not top_packages:
        logger.error(
            'No packages found. Check that the architecture "%s" is correct.', args.arch
        )
        sys.exit(1)

    # --- Tabular Output Logic ---
    # Warn if potentially large output, suggesting redirection
    # Check if stdout is a TTY before warning, and if top is large
    if sys.stdout.isatty() and args.top > 50:
        print(
            f"Warning: Displaying top {args.top} packages. "
            "Consider piping output to 'less' or redirecting to a file (e.g., '> output.txt').",
            file=sys.stderr,
        )

    # Determine column widths
    max_rank_width = len(str(len(top_packages)))
    # Handle case where top_packages might be empty, though checked above
    max_pkg_width = max((len(pkg) for pkg, count in top_packages), default=0)
    max_count_width = max((len(str(count)) for pkg, count in top_packages), default=0)

    # Ensure minimum width for headers
    max_pkg_width = max(max_pkg_width, len("Package"))
    max_count_width = max(max_count_width, len("Files"))
    max_rank_width = max(max_rank_width, len("Rank"))

    # Print header
    header = f"{'Rank':<{max_rank_width}} | {'Package':<{max_pkg_width}} | {'Files':>{max_count_width}}"
    print(header)
    print("-" * len(header))

    # Print rows and gracefully handle broken pipe
    try:
        for rank, (pkg, count) in enumerate(top_packages, start=1):
            print(
                f"{rank:<{max_rank_width}} | {pkg:<{max_pkg_width}} | {count:>{max_count_width}}"
            )
    except BrokenPipeError:
        # Exit main cleanly on broken pipe
        return
    # --- End Tabular Output Logic ---


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Exit silently on broken pipe
        sys.exit(0)
