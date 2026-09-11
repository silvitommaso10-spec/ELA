"""No API key or private key is committed to the repository (CLAUDE.md, spec §52, §58).

A second line of defence next to ``make secrets`` (detect-secrets): a short list of
well-known key formats, scanned over every tracked or unignored file inside ``pytest``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every pattern requires a key body long enough that the pattern's own source (and any
# ``"prefix" + "x" * n`` construction in the tests) never matches it.
PATTERNS: dict[str, re.Pattern[str]] = {
    "Anthropic API key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI API key": re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}"),
    "AWS access key ID": re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Stripe key": re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{20,}"),
    "Telegram bot token": re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"),
    "Private key block": re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----"
    ),
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str
    hint: str  # first characters only: the failure message must not leak the secret

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind} ({self.hint}…)"


def tracked_files(repo_root: Path) -> list[Path]:
    """Files git tracks or would add: the ignore list (``.env``) is honoured."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    ).stdout
    paths = (repo_root / name for name in out.decode("utf-8").split("\0") if name)
    return [path for path in paths if path.is_file()]


def is_binary(path: Path) -> bool:
    with path.open("rb") as fh:
        return b"\0" in fh.read(8192)


def scan_file(path: Path) -> list[Finding]:
    if is_binary(path):
        return []
    findings: list[Finding] = []
    for number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        for kind, pattern in PATTERNS.items():
            match = pattern.search(line)
            if match:
                findings.append(Finding(path, number, kind, match.group(0)[:8]))
    return findings


def scan(paths: list[Path]) -> list[Finding]:
    return [finding for path in paths for finding in scan_file(path)]


def test_repository_has_no_secrets() -> None:
    findings = scan(tracked_files(REPO_ROOT))
    assert not findings, "\n".join(
        str(f.path.relative_to(REPO_ROOT)) + str(f)[len(str(f.path)) :] for f in findings
    )


def test_patterns_do_not_match_their_own_source() -> None:
    """Otherwise this very file would fail the repository scan."""
    assert scan_file(Path(__file__)) == []


# Built at runtime so no key-shaped string appears literally in the repository.
FAKE_SECRETS: dict[str, str] = {
    "Anthropic API key": "sk-ant-" + "api03-" + "k" * 40,
    "OpenAI API key": "sk-" + "proj-" + "o" * 40,
    "AWS access key ID": "AKIA" + "Q" * 16,
    "GitHub token": "ghp_" + "g" * 36,
    "Slack token": "xoxb-" + "1" * 12 + "-" + "s" * 24,
    "Google API key": "AIza" + "z" * 35,
    "Stripe key": "sk_live_" + "t" * 24,
    "Telegram bot token": "1" * 9 + ":AA" + "t" * 33,
    "Private key block": "-----BEGIN " + "PRIVATE KEY-----",
}


@pytest.mark.parametrize("kind", list(PATTERNS))
def test_pattern_is_detected(tmp_path: Path, kind: str) -> None:
    leak = tmp_path / "config.py"
    leak.write_text(f"# comment\nTOKEN = '{FAKE_SECRETS[kind]}'\n", encoding="utf-8")
    kinds = {finding.kind for finding in scan_file(leak)}
    assert kind in kinds
    assert all(finding.line == 2 for finding in scan_file(leak))


def test_finding_does_not_leak_the_secret(tmp_path: Path) -> None:
    leak = tmp_path / "leak.txt"
    leak.write_text(FAKE_SECRETS["AWS access key ID"], encoding="utf-8")
    (finding,) = scan_file(leak)
    assert FAKE_SECRETS["AWS access key ID"] not in str(finding)


def test_clean_file_has_no_findings(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text(
        "API_KEY = os.environ['ANTHROPIC_API_KEY']\nsk-ant- is a prefix\n", encoding="utf-8"
    )
    assert scan_file(clean) == []


def test_binary_files_are_skipped(tmp_path: Path) -> None:
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\0\x01" + FAKE_SECRETS["AWS access key ID"].encode() + b"\0")
    assert scan_file(binary) == []


def test_ignored_files_are_not_scanned(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / ".env").write_text(FAKE_SECRETS["AWS access key ID"], encoding="utf-8")
    (tmp_path / "leak.txt").write_text(FAKE_SECRETS["AWS access key ID"], encoding="utf-8")
    scanned = {path.name for path in tracked_files(tmp_path)}
    assert scanned == {".gitignore", "leak.txt"}
    assert {finding.path.name for finding in scan(tracked_files(tmp_path))} == {"leak.txt"}


DATABASE_FILES = ("ela.db", "ela.db-journal", "ela.db-wal", "ela.db-shm")
"""Every file SQLite writes beside the database: the engine runs in ``journal_mode=WAL``
(``infrastructure/persistence/engine.py:39``, ADR 0006 §12), so the pages not yet checkpointed
live in ``-wal`` and its index in ``-shm`` — the same content as the database, in two more files."""


@pytest.mark.xfail(
    strict=True,
    reason="M12.1 criterio 15: `.gitignore` ignora *.db e *.db-journal ma non i file del WAL — "
    "riparato nel commit seguente, che toglie questo segno",
)
def test_no_file_of_the_database_is_one_git_would_add(tmp_path: Path) -> None:
    """The repository's own ``.gitignore`` against every file of the database (M12.1, D5).

    The default database is in ``~/.ela``, outside the tree; but ``ELA_DB_URL`` can point anywhere,
    and from M12.1 on that file keeps the hashes of the nodes' secrets next to the audit and the
    arguments of every task. What stops ``git add -A`` from taking it is this list and nothing else
    — ``make secrets`` looks at files already tracked, which is after the fact.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(
        (REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for name in DATABASE_FILES:
        (tmp_path / name).write_bytes(b"SQLite format 3\0")

    added = {path.name for path in tracked_files(tmp_path)} & set(DATABASE_FILES)

    assert added == set(), sorted(added)
