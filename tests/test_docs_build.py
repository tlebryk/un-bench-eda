"""Documentation build smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

build_main = pytest.importorskip("sphinx.cmd.build").build_main


def test_html_docs_build(tmp_path: Path) -> None:
    """Docs should build without warnings treated as errors."""
    project_root = Path(__file__).resolve().parents[1]
    source_dir = project_root / "docs" / "source"
    output_dir = tmp_path / "html"

    result = build_main(
        [
            "-b",
            "html",
            "-W",
            "-n",
            str(source_dir),
            str(output_dir),
        ]
    )

    assert result == 0
