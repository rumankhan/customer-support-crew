"""Validate AAMAD project-context artifacts against framework quality gates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_TERMINAL_HEADINGS = (
    "## Sources",
    "## Assumptions",
    "## Open Questions",
    "## Audit",
)

# Artifacts expected after each phase gate (relative to project root).
DEFINE_REQUIRED = (
    "project-context/1.define/prd.md",
    "project-context/1.define/sad.md",
)
DEFINE_OPTIONAL = (
    "project-context/1.define/mrd.md",
)
BUILD_ARTIFACTS = (
    "project-context/2.build/setup.md",
    "project-context/2.build/frontend.md",
    "project-context/2.build/backend.md",
    "project-context/2.build/integration.md",
    "project-context/2.build/qa.md",
)
DELIVER_ARTIFACTS = (
    "project-context/3.deliver/deploy.md",
)

RUNTIME_AUDIT_RE = re.compile(
    r"AAMAD_TARGET_RUNTIME\s*[:=]\s*`?(crewai|claude-agent-sdk|cursor-sdk)`?",
    re.IGNORECASE,
)

KNOWN_CONFIG_TOP_KEYS = frozenset(
    {
        "version",
        "runtime",
        "language",
        "libraries",
        "ui",
        "coding_standards",
        "security",
        "documentation",
        "testing",
    }
)


@dataclass
class ValidationIssue:
    level: str  # "error" | "warning"
    path: str
    message: str


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def add(self, level: str, path: str, message: str) -> None:
        self.issues.append(ValidationIssue(level=level, path=path, message=message))


def _heading_present(text: str, heading: str) -> bool:
    """True if heading appears as a markdown heading (## or ###)."""
    pattern = re.compile(
        rf"^#{{2,3}}\s+{re.escape(heading.lstrip('#').strip())}\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    return bool(pattern.search(text))


def _check_terminal_sections(path: Path, result: ValidationResult) -> None:
    text = path.read_text(encoding="utf-8")
    rel = str(path)
    for heading in REQUIRED_TERMINAL_HEADINGS:
        label = heading.lstrip("#").strip()
        if not _heading_present(text, label):
            result.add("error", rel, f"Missing required heading: {heading}")


def _check_runtime_in_audit(path: Path, result: ValidationResult, *, required: bool) -> None:
    text = path.read_text(encoding="utf-8")
    rel = str(path)
    # Prefer Audit section if present
    audit_match = re.search(
        r"^##\s+Audit\s*$(.*)",
        text,
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    scope = audit_match.group(1) if audit_match else text
    if RUNTIME_AUDIT_RE.search(scope):
        return
    level = "error" if required else "warning"
    result.add(
        level,
        rel,
        "Audit should record resolved AAMAD_TARGET_RUNTIME "
        "(crewai | claude-agent-sdk | cursor-sdk)",
    )


def validate_project(
    root: Path | str,
    *,
    phase: str = "auto",
) -> ValidationResult:
    """
    Validate project-context artifacts under ``root``.

    phase:
      - ``define``: require prd.md + sad.md; mrd.md optional
      - ``build``: define + build artifacts (qa.md required)
      - ``deliver``: build + deploy.md (qa.md gate)
      - ``auto``: validate whatever artifacts exist; enforce gates when later phases appear
    """
    root = Path(root).expanduser().resolve()
    result = ValidationResult()
    phase = phase.lower().strip()

    def exists(rel: str) -> bool:
        return (root / rel).is_file()

    deliver_present = exists(DELIVER_ARTIFACTS[0])
    build_present = any(exists(p) for p in BUILD_ARTIFACTS)
    qa_present = exists("project-context/2.build/qa.md")

    if phase == "auto":
        if deliver_present:
            phase = "deliver"
        elif build_present or qa_present:
            phase = "build"
        else:
            phase = "define"

    # Define gate
    for rel in DEFINE_REQUIRED:
        path = root / rel
        if not path.is_file():
            if phase in ("define", "build", "deliver"):
                result.add("error", rel, "Required Define artifact missing")
            continue
        _check_terminal_sections(path, result)
        if rel.endswith("sad.md"):
            _check_runtime_in_audit(path, result, required=True)

    for rel in DEFINE_OPTIONAL:
        path = root / rel
        if path.is_file():
            _check_terminal_sections(path, result)
        elif phase == "define":
            result.add(
                "warning",
                rel,
                "MRD not found (optional for internal/personal projects)",
            )

    if phase in ("build", "deliver"):
        for rel in BUILD_ARTIFACTS:
            path = root / rel
            if not path.is_file():
                # Only require qa.md hard; others warn if missing mid-build
                level = "error" if rel.endswith("qa.md") else "warning"
                result.add(level, rel, "Build artifact missing")
                continue
            _check_terminal_sections(path, result)
            if rel.endswith(("backend.md", "integration.md", "qa.md")):
                _check_runtime_in_audit(path, result, required=rel.endswith("backend.md"))

    if phase == "deliver":
        if not qa_present:
            result.add(
                "error",
                "project-context/2.build/qa.md",
                "Deliver phase gate failed: qa.md must exist before deploy",
            )
        deploy = root / DELIVER_ARTIFACTS[0]
        if not deploy.is_file():
            result.add("error", DELIVER_ARTIFACTS[0], "Deliver artifact missing")
        else:
            _check_terminal_sections(deploy, result)
            _check_runtime_in_audit(deploy, result, required=True)

    _check_aamad_config(root, result)
    return result


def _check_aamad_config(root: Path, result: ValidationResult) -> None:
    """Validate aamad.config.yml when present (parse + known top-level keys)."""
    path = root / "aamad.config.yml"
    if not path.is_file():
        return
    rel = "aamad.config.yml"
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - parse errors
        result.add("error", rel, f"Failed to parse YAML: {exc}")
        return
    if data is None:
        result.add("warning", rel, "Config file is empty")
        return
    if not isinstance(data, dict):
        result.add("error", rel, "Config root must be a mapping")
        return
    unknown = sorted(set(data.keys()) - KNOWN_CONFIG_TOP_KEYS)
    if unknown:
        result.add(
            "error",
            rel,
            f"Unknown top-level key(s): {', '.join(unknown)}",
        )


def format_report(result: ValidationResult) -> str:
    if not result.issues:
        return "OK: no validation issues found."
    lines = []
    for issue in result.issues:
        lines.append(f"[{issue.level.upper()}] {issue.path}: {issue.message}")
    summary = "PASSED" if result.ok else "FAILED"
    lines.append(f"\nValidation {summary} ({len(result.issues)} issue(s)).")
    return "\n".join(lines)
