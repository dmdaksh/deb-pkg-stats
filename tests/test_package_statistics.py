import gzip
import io
import logging
import sys
from email.message import Message
from io import TextIOWrapper
from typing import Any, cast
from urllib.error import HTTPError, URLError

import pytest

import package_statistics
from package_statistics import (
    DEFAULT_COMPONENT,
    DEFAULT_DIST,
    DEFAULT_MIRROR,
    download_contents,
    get_top_packages,
    main,
    parse_contents,
)


class DummyResponse:
    """
    Dummy HTTP response for urlopen.
    Implements read() and close() to avoid cleanup warnings.
    """

    def __init__(self, status: int, data: bytes, headers: dict[str, str] | None = None):
        self.status = status
        self._data = data
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        """No-op close for compatibility."""
        return None

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any | None,
    ) -> None:
        self.close()
        # Returning None (or omitting return) indicates exception should re-raise if present

    # Optional: support file-like iterator for gzip
    def readinto(self, b: bytearray) -> int:
        data = self.read()
        n = min(len(data), len(b))
        b[:n] = data[:n]
        return n

    def readline(self, *args: Any, **kwargs: Any) -> bytes:
        # Not needed for these tests
        return b""


# -------- parse_contents tests --------


def test_parse_contents_basic() -> None:
    lines = [
        "bin/foo pkgA",
        "bin/bar    pkgB,pkgC",
    ]
    stream = cast(TextIOWrapper, io.StringIO("\n".join(lines)))
    result = list(parse_contents(stream))
    assert result == ["pkgA", "pkgB", "pkgC"]


def test_parse_contents_spaces_in_path() -> None:
    lines = [
        "path with spaces/foo   area/pkgA,section/pkgB",
    ]
    stream = cast(TextIOWrapper, io.StringIO("\n".join(lines)))
    result = list(parse_contents(stream))
    assert result == ["pkgA", "pkgB"]


def test_parse_contents_blank_and_malformed() -> None:
    lines = ["", "   ", "no_delimiter_line"]
    stream = cast(TextIOWrapper, io.StringIO("\n".join(lines)))
    result = list(parse_contents(stream))
    assert result == []


def test_parse_contents_qualified_names() -> None:
    lines = [
        "path/file1 area/section/pkgA",
        "path/file2 other/pkgB,another/pkgC",
        "path/file3 pkgD",  # No area/section
    ]
    stream = cast(TextIOWrapper, io.StringIO("\n".join(lines)))
    result = list(parse_contents(stream))
    # Should extract only the package name part
    assert result == ["pkgA", "pkgB", "pkgC", "pkgD"]


def test_parse_contents_header_line() -> None:
    # Should skip the header line if present
    lines = ["FILE          LOCATION", "bin/actual    pkgA"]
    stream = cast(TextIOWrapper, io.StringIO("\n".join(lines)))
    result = list(parse_contents(stream))
    assert result == ["pkgA"]


# -------- download_contents tests --------


@pytest.fixture(autouse=True)
def patch_urlopen(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    """
    Fixture to provide dummy urlopen behaviors.
    """

    def dummy_success(url: str) -> DummyResponse:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(b"bin/foo pkgA,pkgB\n")
        buf.seek(0)
        return DummyResponse(
            200, buf.read(), headers={"Content-Type": "application/gzip"}
        )

    def dummy_error(url: str) -> None:
        raise URLError("Download failed")

    monkeypatch.setattr(package_statistics, "urlopen", dummy_success)
    return dummy_success, dummy_error


def test_download_contents_success(
    monkeypatch: pytest.MonkeyPatch, patch_urlopen: Any
) -> None:
    success_fn, _ = patch_urlopen
    monkeypatch.setattr(
        package_statistics, "urlopen", success_fn
    )  # Revert setattr path
    data = download_contents("amd64", DEFAULT_MIRROR, DEFAULT_DIST, DEFAULT_COMPONENT)
    assert isinstance(data, io.BytesIO)
    assert data.getbuffer().nbytes > 0


def test_download_contents_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_status(url: str) -> DummyResponse:
        return DummyResponse(404, b"", headers={})

    monkeypatch.setattr(
        package_statistics, "urlopen", bad_status
    )  # Revert setattr path
    with pytest.raises(HTTPError):
        download_contents("amd64", DEFAULT_MIRROR, DEFAULT_DIST, DEFAULT_COMPONENT)


def test_download_contents_url_error(
    monkeypatch: pytest.MonkeyPatch, patch_urlopen: Any
) -> None:
    _, error_fn = patch_urlopen
    monkeypatch.setattr(package_statistics, "urlopen", error_fn)  # Revert setattr path
    with pytest.raises(URLError):
        download_contents("amd64", DEFAULT_MIRROR, DEFAULT_DIST, DEFAULT_COMPONENT)


# -------- get_top_packages tests --------


def test_get_top_packages_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str) -> DummyResponse:
        raw = b"bin/a pkgX,pkgY\nbin/b pkgX\n"
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(raw)
        buf.seek(0)
        return DummyResponse(200, buf.read(), headers={})

    monkeypatch.setattr(
        package_statistics, "urlopen", fake_urlopen
    )  # Revert setattr path
    top = get_top_packages("amd64", top_n=2)
    assert top == [("pkgX", 2), ("pkgY", 1)]


def test_get_top_packages_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen_empty(url: str) -> DummyResponse:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(b"")
        buf.seek(0)
        return DummyResponse(200, buf.read(), headers={})

    monkeypatch.setattr(
        package_statistics, "urlopen", fake_urlopen_empty
    )  # Revert setattr path
    top = get_top_packages("amd64", top_n=5)
    assert top == []


def test_get_top_packages_more_than_available(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str) -> DummyResponse:
        raw = b"bin/a pkgX,pkgY\nbin/b pkgX\n"
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(raw)
        buf.seek(0)
        return DummyResponse(200, buf.read(), headers={})

    monkeypatch.setattr(
        package_statistics, "urlopen", fake_urlopen
    )  # Revert setattr path
    # Request 5, only 2 unique packages exist
    top = get_top_packages("amd64", top_n=5)
    assert top == [("pkgX", 2), ("pkgY", 1)]


def test_get_top_packages_top_n_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str) -> DummyResponse:
        raw = b"bin/a pkgX,pkgY\nbin/b pkgX\n"
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(raw)
        buf.seek(0)
        return DummyResponse(200, buf.read(), headers={})

    monkeypatch.setattr(
        package_statistics, "urlopen", fake_urlopen
    )  # Revert setattr path
    top = get_top_packages("amd64", top_n=0)
    assert top == []


def test_get_top_packages_ties(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str) -> DummyResponse:
        raw = b"f1 pkgA\nf2 pkgB\nf3 pkgA\nf4 pkgB\nf5 pkgC\n"
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(raw)
        buf.seek(0)
        return DummyResponse(200, buf.read(), headers={})

    monkeypatch.setattr(
        package_statistics, "urlopen", fake_urlopen
    )  # Revert setattr path
    top = get_top_packages("amd64", top_n=3)
    # Order of ties (pkgA, pkgB) might vary, so check contents
    assert len(top) == 3
    assert ("pkgC", 1) in top
    assert ("pkgA", 2) in top
    assert ("pkgB", 2) in top


def test_get_top_packages_download_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen_error(url: str) -> None:
        # Need to fix the HTTPError arguments to match expected types
        # The 4th argument should be hdrs: email.message.Message | None
        # The 5th argument should be fp: IO[Any] | None
        # Passing an empty Message object for headers and None for fp
        raise HTTPError(
            url, 404, "Not Found", Message(), None
        )  # Changed None to Message() for headers

    monkeypatch.setattr(
        package_statistics, "urlopen", fake_urlopen_error
    )  # Revert setattr path
    with pytest.raises(HTTPError):
        get_top_packages("amd64", top_n=5)


# -------- main() / CLI tests --------


def test_main_success_defaults(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test successful run with default arguments."""
    mock_data = [("pkgA", 10), ("pkgB", 5)]
    monkeypatch.setattr(
        package_statistics,
        "get_top_packages",
        lambda *args, **kwargs: mock_data,  # Revert setattr path
    )
    monkeypatch.setattr(sys, "argv", ["package_statistics.py", "amd64"])

    main()

    captured = capsys.readouterr()
    # No stderr
    assert captured.err == ""
    # Split output into lines
    lines = captured.out.strip().splitlines()
    # Header line
    assert lines[0] == "Rank | Package | Files"
    # Underline line of dashes matching header length
    assert set(lines[1]) == {"-"}
    assert len(lines[1]) == len(lines[0])
    # Data rows
    assert lines[2].strip().startswith("1    |")
    assert "pkgA" in lines[2] and lines[2].strip().endswith("10")
    assert lines[3].strip().startswith("2    |")
    assert "pkgB" in lines[3] and lines[3].strip().endswith("5")
    # Only 4 lines total
    assert len(lines) == 4


def test_main_success_custom_args(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test successful run with --arch and --top arguments."""
    mock_data = [("pkgX", 1)]

    def mock_get_top(
        arch: str, top_n: int, *args: Any, **kwargs: Any
    ) -> list[tuple[str, int]]:
        assert arch == "arm64"
        assert top_n == 1
        return mock_data

    monkeypatch.setattr(
        package_statistics, "get_top_packages", mock_get_top
    )  # Revert setattr path
    monkeypatch.setattr(sys, "argv", ["package_statistics.py", "arm64", "--top", "1"])

    main()

    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.strip().splitlines()
    assert lines[0] == "Rank | Package | Files"
    assert set(lines[1]) == {"-"}
    assert len(lines[1]) == len(lines[0])
    assert lines[2].strip().startswith("1    |")
    assert "pkgX" in lines[2] and lines[2].strip().endswith("1")
    assert len(lines) == 3


def test_main_download_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture,
) -> None:
    """Test handling of download errors (e.g., HTTPError)."""
    caplog.set_level(logging.ERROR, logger="package_statistics")

    def mock_get_top_error(*args: Any, **kwargs: Any) -> list[tuple[str, int]]:
        raise HTTPError("http://example.com", 500, "Server Error", Message(), None)

    monkeypatch.setattr(
        package_statistics, "get_top_packages", mock_get_top_error
    )  # Revert setattr path
    monkeypatch.setattr(sys, "argv", ["package_statistics.py", "amd64"])

    with pytest.raises(SystemExit) as excinfo:
        main()
    # Exit code 1
    assert excinfo.value.code == 1
    # stdout is empty
    captured = capsys.readouterr()
    assert captured.out == ""
    # Error logged
    errors = [rec.message for rec in caplog.records if rec.levelno == logging.ERROR]
    assert any(
        "An unexpected error occurred: HTTP Error 500: Server Error" in msg
        for msg in errors
    )


def test_main_invalid_top_arg(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test handling of invalid --top argument."""
    # No need to mock get_top_packages as argparse should fail first
    monkeypatch.setattr(sys, "argv", ["package_statistics.py", "--top", "not-a-number"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code != 0  # argparse usually exits with 2 for bad args
    captured = capsys.readouterr()
    assert "argument --top: invalid int value: 'not-a-number'" in captured.err
    assert captured.out == ""


def test_main_large_output_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test that main prints a warning to stderr when top > 50 and stdout is a TTY."""
    mock_data = [("pkgA", 1)]
    monkeypatch.setattr(
        package_statistics,
        "get_top_packages",
        lambda *args, **kwargs: mock_data,  # Revert setattr path
    )
    monkeypatch.setattr(sys, "argv", ["package_statistics.py", "amd64", "--top", "51"])
    # Simulate TTY
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    main()
    captured = capsys.readouterr()
    # Warning should go to stderr
    assert "Warning: Displaying top 51 packages" in captured.err
    # Header still printed to stdout
    assert captured.out.splitlines()[0] == "Rank | Package | Files"


def test_main_broken_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that main exits cleanly (returns) on BrokenPipeError."""
    mock_data = [("pkgA", 1), ("pkgB", 2)]
    monkeypatch.setattr(
        package_statistics,
        "get_top_packages",
        lambda *args, **kwargs: mock_data,  # Revert setattr path
    )
    monkeypatch.setattr(sys, "argv", ["package_statistics.py", "amd64"])
    # Replace print to raise BrokenPipeError on the first data row
    import builtins

    call_count = {"n": 0}
    original_print = builtins.print

    def fake_print(*args: Any, **kwargs: Any) -> None:
        call_count["n"] += 1
        # Calls: 1=header, 2=underline, 3=first row -> raise
        if call_count["n"] == 3:
            raise BrokenPipeError
        return original_print(*args, **kwargs)

    monkeypatch.setattr(builtins, "print", fake_print)

    # Call main() and expect it to return without raising an unexpected exception
    # (The BrokenPipeError is caught and handled by returning)
    try:
        main()
    except BrokenPipeError:
        pytest.fail("BrokenPipeError should have been caught inside main()")
    # No SystemExit expected anymore
