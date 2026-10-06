"""Extraction checks for independent commands and immutable packaged prompt bytes."""

from pathlib import Path

import pytest
from src.cli import main
from src.db.migrate import heads
from src.llm.prompt import build_prompt


def test_default_prompt_and_revision_graph_work_outside_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert build_prompt().system_prompt_hash == (
        "f9754a11f4e9e0ba438c1f2d9062fa9511d57dc67789346ff01fc4e18489b794"
    )
    assert heads() == ["008_measurement_basis"]


@pytest.mark.parametrize("command", ["portal", "admin", "publish", "unpublish", "decide"])
def test_removed_surface_commands_name_their_new_owner(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([command]) == 2
    expected = "alerts-bi-portal" if command == "portal" else "alerts-bi-admin"
    message = capsys.readouterr().err
    assert expected in message
    if command == "portal":
        assert "alerts-bi-portal." in message
