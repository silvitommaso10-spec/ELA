"""The `make secrets` target (detect-secrets-hook) fails when a secret is present."""

from pathlib import Path

from detect_secrets.pre_commit_hook import main

# Built at runtime so the pattern never appears literally in the repository.
FAKE_AWS_KEY = "AKIA" + "Q" * 16


def test_clean_file_passes(tmp_path: Path) -> None:
    clean = tmp_path / "clean.txt"
    clean.write_text("nothing to see here\n", encoding="utf-8")
    assert main([str(clean)]) == 0


def test_file_with_secret_fails(tmp_path: Path) -> None:
    leak = tmp_path / "leak.txt"
    leak.write_text(f'aws_key = "{FAKE_AWS_KEY}"\n', encoding="utf-8")
    assert main([str(leak)]) == 1
