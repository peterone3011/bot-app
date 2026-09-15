from __future__ import annotations

from pathlib import Path

from scripts import validate_projects


def test_preflight_validates_without_starting_discord_or_feishu(tmp_path: Path, capsys) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "alpha.yaml").write_text(
        """
project:
  slug: alpha
  brand_name: Alpha
discord:
  token_env: DISCORD_TOKEN_ALPHA
  guild_id: "101"
  admin_role_ids: ["401"]
  manual_embed_channel_ids: ["501"]
features:
  manual_embed: true
  role_selector: false
  auto_reaction: false
  exclusive_updates_reaction: false
  daily_updates: false
  community_metrics: false
channels: {}
""",
        encoding="utf-8",
    )

    result = validate_projects.main(
        ["--projects", "alpha"],
        repo_root=tmp_path,
        environ={"DISCORD_TOKEN_ALPHA": "not-printed"},
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "OK alpha guild=101 features=manual_embed" in output
    assert "not-printed" not in output
