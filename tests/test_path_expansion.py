from pathlib import Path

from pathtree.utils.path import normalize_path


def test_path_expansion_home() -> None:
    """Verify that ~ and ~/ expand to home."""
    home_dir = str(Path.home().resolve())

    norm_tilde = normalize_path("~")
    norm_slash = normalize_path("~/")

    assert norm_tilde == home_dir
    assert norm_slash == home_dir


def test_path_expansion_below_home() -> None:
    """Verify that valid path below home expands correctly."""
    home_dir = Path.home().resolve()
    target_path = home_dir / "downloads"

    norm_path = normalize_path("~/downloads")
    assert norm_path == str(target_path)


def test_path_expansion_partial_username() -> None:
    """Verify that partial username like ~w and ~ws/ does not raise RuntimeError."""
    # These should gracefully fallback and NOT raise RuntimeError/traceback
    norm_w = normalize_path("~w")
    norm_ws = normalize_path("~ws/")

    assert norm_w is not None
    assert norm_ws is not None


def test_path_expansion_unknown_username() -> None:
    """Verify that unknown ~username/ expands safely or preserves input."""
    norm_unknown = normalize_path("~unknown_user_12345/")
    assert norm_unknown is not None


def test_path_expansion_none_and_empty() -> None:
    """Verify that None and empty string normalization works safely."""
    assert normalize_path(None) is None
    assert normalize_path("") == ""
    assert normalize_path("   ") == ""
