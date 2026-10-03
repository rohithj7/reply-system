"""Audit the submission's tracked tree and, with --history, every commit reachable from any ref.

Usage:
    uv run python scripts/audit_submission.py [--history] [--repo PATH]

Fails on planning files, weights, large blobs, LFS, secrets, references to private
repositories, a changed packet, stale resource manifests and banned export content.
Standard library only; prints each finding and exits non-zero if there are any.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

PACKET_PATH = "docs/assignment/pre-deposit-respond-packet.md"
PACKET_SHA256 = "d06e044a4e3e13b4bc72343593c15cf05196cd51c8eee671c9d05a2cfc6e7436"
MAX_BLOB_BYTES = 5 * 1024 * 1024
WEIGHT_EXTENSIONS = (".safetensors", ".gguf", ".bin", ".pt", ".pth", ".onnx", ".ckpt", ".h5")
PLANNING_PROMPT = "doctours-cursor-planning-prompt"
# Built by concatenation so this file does not contain the name it bans.
PRIVATE_REPO = re.compile("doctours" + "[-_]ml", re.IGNORECASE)
SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}|\bgithub_pat_[A-Za-z0-9_]{22,}"),
    "API key (sk-)": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
}
EXPORT_DIRS = ("resources/", "datasets/", "eval/")
BANNED_EXPORT_SUBSTRINGS = ("<think>", "</think>", "reasoning_content")
RESOURCE_MANIFESTS = {
    "resources/fixtures/manifest.json": ("fixtures", "files", "path"),
    "resources/policy_sets/manifest.json": ("policy_sets", "modules", "path"),
    "datasets/manifest.json": ("files", None, "file"),
}
DATASET_ROW_KEYS = frozenset(
    {
        "case_id",
        "split",
        "fixture_id",
        "policy_set_id",
        "controller_io_version",
        "message",
        "steps",
        "outcome",
        "reply",
        "labels",
    }
)


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, capture_output=True, check=True
    ).stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_problem(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if re.search(r"(^|/)\.cursor/plans/", path) or path.endswith(".plan.md"):
        return "planning file"
    if PLANNING_PROMPT in name:
        return "planning prompt"
    if name.lower().endswith(WEIGHT_EXTENSIONS):
        return "model weights"
    if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
        return "environment file"
    if PRIVATE_REPO.search(path):
        return "private repository name"
    return None


def _text_problems(text: str, where: str, path: str) -> Iterable[str]:
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            yield f"secret: {label} in {where}"
    if PRIVATE_REPO.search(text):
        yield f"reference: private repository name in {where}"
    if path.endswith(".gitattributes") and "filter=lfs" in text:
        yield f"lfs: LFS entry in {where}"


def _tracked_findings(repo: Path) -> list[str]:
    findings: list[str] = []
    paths = [p for p in _git(repo, "ls-files", "-z").decode().split("\0") if p]
    for path in paths:
        if problem := _path_problem(path):
            findings.append(f"path: {problem}: {path}")
        file = repo / path
        if not file.is_file():
            continue
        data = file.read_bytes()
        if len(data) > MAX_BLOB_BYTES:
            findings.append(f"size: {path} is {len(data)} bytes")
        if b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        findings.extend(_text_problems(text, path, path))
        if path.startswith(EXPORT_DIRS):
            findings.extend(
                f"export: banned substring {s!r} in {path}"
                for s in BANNED_EXPORT_SUBSTRINGS
                if s in text
            )
    packet = repo / PACKET_PATH
    if not packet.is_file() or _sha256(packet) != PACKET_SHA256:
        findings.append(f"packet: {PACKET_PATH} is missing or differs from the assignment")
    findings.extend(_manifest_findings(repo, paths))
    return findings


def _manifest_findings(repo: Path, tracked: list[str]) -> list[str]:
    findings: list[str] = []
    for manifest_path, (list_key, files_key, path_key) in RESOURCE_MANIFESTS.items():
        base = manifest_path.rsplit("/", 1)[0] + "/"
        under_base = [p for p in tracked if p.startswith(base) and p != manifest_path]
        manifest_file = repo / manifest_path
        if not manifest_file.is_file():
            if manifest_path.startswith("resources/") or under_base:
                findings.append(f"manifest: {manifest_path} is missing")
            continue
        try:
            entries = json.loads(manifest_file.read_text("utf-8"))[list_key]
            files = [f for e in entries for f in (e[files_key] if files_key else [e])]
            listed = {f[path_key]: f["sha256"] for f in files}
        except (ValueError, KeyError, TypeError) as exc:
            findings.append(f"manifest: {manifest_path} is malformed: {exc!r}")
            continue
        for relative, expected in listed.items():
            target = repo / base / relative
            if not target.is_file():
                findings.append(f"manifest: {manifest_path} lists missing {relative}")
            elif _sha256(target) != expected:
                findings.append(f"manifest: sha256 mismatch for {base}{relative}")
        for path in under_base:
            if path[len(base) :] not in listed:
                findings.append(f"manifest: {path} is not listed in {manifest_path}")
        if manifest_path.startswith("datasets/"):
            findings.extend(_dataset_row_findings(repo, base, listed))
    return findings


def _dataset_row_findings(repo: Path, base: str, listed: dict[str, str]) -> Iterable[str]:
    for relative in listed:
        target = repo / base / relative
        if not relative.endswith(".jsonl") or not target.is_file():
            continue
        for number, line in enumerate(target.read_text("utf-8").splitlines(), 1):
            extra = set(json.loads(line)) - DATASET_ROW_KEYS if line.strip() else set()
            if extra:
                yield f"export: {base}{relative}:{number} has non-allowlisted keys {sorted(extra)}"


def _history_findings(repo: Path) -> list[str]:
    findings: list[str] = []
    for path in set(_git(repo, "log", "--all", "--format=", "--name-only").decode().splitlines()):
        if path and (problem := _path_problem(path)):
            findings.append(f"history path: {problem}: {path}")
    objects = _git(repo, "rev-list", "--objects", "--all")
    sizes = _git(
        repo, "cat-file", "--batch-check=%(objecttype) %(objectsize) %(rest)", stdin=objects
    )
    for line in sizes.decode().splitlines():
        kind, size, *rest = line.split(" ", 2)
        if kind == "blob" and int(size) > MAX_BLOB_BYTES:
            findings.append(f"history size: {rest[0] if rest else '?'} is {size} bytes")
    current = ""
    diff = _git(repo, "log", "--all", "-p", "--no-color", "--no-ext-diff", "--format=")
    for line in diff.decode("utf-8", errors="replace").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+"):
            findings.extend(
                f"history {problem}" for problem in _text_problems(line[1:], current, current)
            )
    messages = _git(repo, "log", "--all", "--format=%B").decode("utf-8", errors="replace")
    findings.extend(
        f"history {problem}" for problem in _text_problems(messages, "commit messages", "")
    )
    return findings


def run_audit(repo: Path, history: bool) -> list[str]:
    findings = _tracked_findings(repo)
    if history:
        findings.extend(_history_findings(repo))
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history", action="store_true", help="also audit all commits")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    findings = run_audit(args.repo.resolve(), args.history)
    for finding in findings:
        print(finding)
    scope = "tracked tree and full history" if args.history else "tracked tree"
    print(f"audit {'failed' if findings else 'passed'}: {len(findings)} findings ({scope})")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
