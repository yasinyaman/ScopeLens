"""Input validation unit tests: git URL allow-list + identifier (path-traversal) protection."""

import pytest
from etki.adapters.git_clone import GitCloneError, _validate_git_url
from etki.projects_store import _validate_id


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ext::sh -c id",
        "-c core.something=evil",
        "--upload-pack=evil",
        "/local/path/repo",
        "https://localhost/x",
        "https://127.0.0.1/x.git",
        "git://10.0.0.1/x",
        "ssh://[::1]/x",
        "https://192.168.1.5/x",
    ],
)
def test_git_url_rejected(url: str) -> None:
    with pytest.raises(GitCloneError):
        _validate_git_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/org/repo.git",
        "git@github.com:org/repo.git",
        "ssh://git@gitlab.com/org/repo.git",
    ],
)
def test_git_url_allowed(url: str) -> None:
    _validate_git_url(url)  # must not raise


@pytest.mark.parametrize("bad", ["../etc", "a/b", "x..y", "with space", "", "abs/../x", "/root"])
def test_identifier_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        _validate_id(bad, "proje id")


@pytest.mark.parametrize("ok", ["demo", "shop_b", "proj-1", "ABC123"])
def test_identifier_allowed(ok: str) -> None:
    assert _validate_id(ok) == ok
