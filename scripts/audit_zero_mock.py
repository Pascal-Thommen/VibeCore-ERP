#!/usr/bin/env python3
"""
Zero-Mock & Architecture Audit Tool for Gatekeeper CI (VibeCore ERP).

Enforces the Zero Mock Doktrin and software-testing-audit requirements:
1. Absolutes Verbot von Demos, Scheinoberflächen, Dummy-Buttons und Mocks im Produktivcode.
2. Keine Scheintests (Tests ohne Assertions oder Stubs).
3. Einhaltung der 4 Kernsäulen (Resilienz/Timeouts, ACID, Sicherheit, Observability).
4. VibeCore Core-Invarianz (keine Adapter-Imports im Core, keine Core-DB-Zugriffe).

Returns exit code 0 if all checks pass, 1 if any violation is found.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditViolation:
    rule_id: str
    severity: str  # "BLOCKER" or "WARNING"
    file_path: Path
    line_number: int
    message: str
    code_snippet: str | None = None


@dataclass
class AuditStats:
    total_files_scanned: int = 0
    production_files_scanned: int = 0
    test_files_scanned: int = 0
    violations: list[AuditViolation] = field(default_factory=list)

    @property
    def blocker_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "BLOCKER")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "WARNING")


class ZeroMockAuditor:
    # Forbidden mock module names in production code
    FORBIDDEN_PROD_MOCK_MODULES = {
        "unittest.mock",
        "mock",
        "pytest_mock",
    }

    # Forbidden mock classes or objects in production code
    FORBIDDEN_PROD_MOCK_NAMES = {
        "Mock",
        "MagicMock",
        "patch",
        "AsyncMock",
        "PropertyMock",
        "create_autospec",
        "NonCallableMock",
    }

    # Forbidden bypass or dummy flags when assigned True/1
    FORBIDDEN_BYPASS_FLAGS = {
        "MOCK_MODE",
        "ENABLE_MOCK",
        "ENABLE_MOCKS",
        "USE_MOCK",
        "USE_MOCKS",
        "SKIP_AUTH",
        "BYPASS_AUTH",
        "BYPASS_SECURITY",
        "USE_FAKE_DATA",
        "USE_MOCK_GATEWAY",
        "MOCK_PAYMENT",
    }

    # HTTP client call functions that require an explicit timeout
    HTTP_CALL_NAMES = {
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "request",
        "Client",
        "AsyncClient",
    }

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.stats = AuditStats()

    def is_test_file(self, path: Path) -> bool:
        parts = path.parts
        if "tests" in parts or "test" in parts:
            return True
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return True
        if path.name == "conftest.py":
            return True
        return False

    def is_ignored_path(self, path: Path) -> bool:
        parts = path.parts
        ignored_names = {
            ".git",
            ".venv",
            ".venv-vibecore",
            "venv",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            "node_modules",
            ".ai",
            "build",
            "dist",
            ".eggs",
        }
        return any(part in ignored_names for part in parts)

    def scan_all(self) -> AuditStats:
        python_files: list[Path] = []
        for p in self.root_dir.rglob("*.py"):
            if not self.is_ignored_path(p):
                python_files.append(p)

        self.stats.total_files_scanned = len(python_files)

        for file_path in python_files:
            rel_path = file_path.relative_to(self.root_dir)
            if self.is_test_file(file_path):
                self.stats.test_files_scanned += 1
                self.audit_test_file(file_path, rel_path)
            else:
                self.stats.production_files_scanned += 1
                self.audit_production_file(file_path, rel_path)

        # Microservice health check verification
        self.audit_healthchecks()

        return self.stats

    def _get_line_snippet(self, file_path: Path, line_number: int) -> str | None:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                if 1 <= line_number <= len(lines):
                    return lines[line_number - 1].strip()
        except Exception:
            pass
        return None

    def add_violation(
        self,
        rule_id: str,
        severity: str,
        file_path: Path,
        line_number: int,
        message: str,
    ) -> None:
        snippet = self._get_line_snippet(file_path, line_number)
        self.stats.violations.append(
            AuditViolation(
                rule_id=rule_id,
                severity=severity,
                file_path=file_path.relative_to(self.root_dir),
                line_number=line_number,
                message=message,
                code_snippet=snippet,
            )
        )

    def audit_production_file(self, file_path: Path, rel_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            self.add_violation(
                "SYNTAX_ERROR",
                "BLOCKER",
                file_path,
                e.lineno or 1,
                f"Syntax error in production file: {e.msg}",
            )
            return

        for node in ast.walk(tree):
            # Check 1: Forbidden mock library imports in production
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_PROD_MOCK_MODULES or alias.name.startswith(
                        "unittest.mock"
                    ):
                        self.add_violation(
                            "NO_PROD_MOCKS",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                f"Production code imports forbidden mock module '{alias.name}'. "
                                "Mocks are prohibited in production code per Zero Mock Doktrin."
                            ),
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in self.FORBIDDEN_PROD_MOCK_MODULES or mod.startswith("unittest.mock"):
                    self.add_violation(
                        "NO_PROD_MOCKS",
                        "BLOCKER",
                        file_path,
                        node.lineno,
                        (
                            f"Production code imports from forbidden mock module '{mod}'. "
                            "Mocks are strictly prohibited in production code."
                        ),
                    )
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_PROD_MOCK_NAMES:
                        self.add_violation(
                            "NO_PROD_MOCKS",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                f"Production code imports forbidden mock object '{alias.name}'. "
                                "Mocks are prohibited in production code."
                            ),
                        )

            # Check 2: Core Invariance - backend/app must NEVER import from adapters
            if "backend" in rel_path.parts and "app" in rel_path.parts:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("adapters") or alias.name.startswith(
                            "vibecore_adapter"
                        ):
                            self.add_violation(
                                "CORE_INVARIANCE",
                                "BLOCKER",
                                file_path,
                                node.lineno,
                                (
                                    "Core Invariance Violation: Finance Core cannot depend on "
                                    f"external adapter '{alias.name}'."
                                ),
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod.startswith("adapters") or mod.startswith("vibecore_adapter"):
                        self.add_violation(
                            "CORE_INVARIANCE",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                "Core Invariance Violation: Finance Core cannot import from "
                                f"external adapter '{mod}'."
                            ),
                        )

            # Check 3: Adapter Isolation - no direct backend DB session/engine
            if "adapters" in rel_path.parts:
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod == "app.db.base" or mod.startswith("app.db"):
                        self.add_violation(
                            "ADAPTER_ISOLATION",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                f"Adapter Isolation Violation: imports core DB module '{mod}'. "
                                "Adapters must communicate via REST API / SDK only."
                            ),
                        )

            # Check 4: Bypass flags
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in self.FORBIDDEN_BYPASS_FLAGS:
                        # Check if assigned True
                        if isinstance(node.value, ast.Constant) and node.value.value in (
                            True,
                            "true",
                            "True",
                            1,
                        ):
                            self.add_violation(
                                "NO_MOCK_FLAGS",
                                "BLOCKER",
                                file_path,
                                node.lineno,
                                (
                                    f"Bypass/Mock flag: '{target.id} = {node.value.value}'. "
                                    "Bypasses forbidden per Zero Mock Doktrin."
                                ),
                            )

            # Check 5: Unimplemented Stubs in functions (pass or NotImplementedError only)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Ignore abstractmethods or protocols
                decorator_names = [
                    d.id
                    if isinstance(d, ast.Name)
                    else (d.attr if isinstance(d, ast.Attribute) else "")
                    for d in node.decorator_list
                ]
                if any("abstractmethod" in dec for dec in decorator_names):
                    continue

                # Ignore dunder methods like __init__
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue

                # Check body for single pass or single raise NotImplementedError
                statements = [
                    s
                    for s in node.body
                    if not (
                        isinstance(s, ast.Expr)
                        and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str)
                    )
                ]
                if len(statements) == 1:
                    stmt = statements[0]
                    if isinstance(stmt, ast.Pass):
                        self.add_violation(
                            "NO_EMPTY_STUBS",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                f"Function '{node.name}' is an empty stub ('pass'). "
                                "Full implementation with real business logic required."
                            ),
                        )
                    elif isinstance(stmt, ast.Raise):
                        exc = stmt.exc
                        is_not_implemented = False
                        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                            is_not_implemented = True
                        elif (
                            isinstance(exc, ast.Call)
                            and isinstance(exc.func, ast.Name)
                            and exc.func.id == "NotImplementedError"
                        ):
                            is_not_implemented = True
                        if is_not_implemented:
                            self.add_violation(
                                "NO_EMPTY_STUBS",
                                "BLOCKER",
                                file_path,
                                node.lineno,
                                (
                                    f"Function '{node.name}' raises NotImplementedError. "
                                    "Full implementation required per Zero Mock Doktrin."
                                ),
                            )

            # Check 6: Timeouts on external HTTP network calls (Säule 1)
            if isinstance(node, ast.Call):
                func = node.func
                is_http_call = False
                call_name = ""
                if isinstance(func, ast.Attribute):
                    call_name = func.attr
                    if isinstance(func.value, ast.Name) and func.value.id in ("httpx", "requests"):
                        if call_name in self.HTTP_CALL_NAMES:
                            is_http_call = True
                if is_http_call:
                    has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                    if not has_timeout:
                        self.add_violation(
                            "REQUIRE_TIMEOUTS",
                            "WARNING",
                            file_path,
                            node.lineno,
                            (
                                f"External HTTP call '{call_name}' lacks explicit timeout. "
                                "Säule 1 requires explicit timeouts."
                            ),
                        )

    def audit_test_file(self, file_path: Path, rel_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            self.add_violation(
                "SYNTAX_ERROR",
                "BLOCKER",
                file_path,
                e.lineno or 1,
                f"Syntax error in test file: {e.msg}",
            )
            return

        # conftest.py defines fixtures and hooks, not test functions
        if file_path.name == "conftest.py":
            return

        for node in ast.walk(tree):
            # Check 7: Anti-Scheintest Validation (Tests must have assertions)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                # Ignore functions decorated with @pytest.fixture or @fixture
                decorator_names = [
                    d.id
                    if isinstance(d, ast.Name)
                    else (d.attr if isinstance(d, ast.Attribute) else "")
                    for d in node.decorator_list
                ]
                if any("fixture" in dec for dec in decorator_names):
                    continue

                # Collect asserts or verifications
                has_assert = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assert):
                        has_assert = True
                        break
                    if isinstance(sub, ast.With):
                        for item in sub.items:
                            # e.g., with pytest.raises(...)
                            ctx = item.context_expr
                            if isinstance(ctx, ast.Call):
                                if isinstance(ctx.func, ast.Attribute) and ctx.func.attr in (
                                    "raises",
                                    "warns",
                                ):
                                    has_assert = True
                                    break
                    if isinstance(sub, ast.Call):
                        if isinstance(sub.func, ast.Attribute) and (
                            sub.func.attr.startswith("assert_")
                            or sub.func.attr in ("raise_for_status", "fail")
                        ):
                            has_assert = True
                            break

                # Check if body is just pass
                is_just_pass = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)

                if is_just_pass or not has_assert:
                    self.add_violation(
                        "NO_SCHEINTESTS",
                        "BLOCKER",
                        file_path,
                        node.lineno,
                        (
                            f"Scheintest detected: test '{node.name}' has no assertions. "
                            "Tests must rigorously verify behavior."
                        ),
                    )

    def audit_healthchecks(self) -> None:
        # Check that microservices have a health check route
        # Look for FastAPI app instances in backend and adapters
        services = [
            ("Finance Core Backend", self.root_dir / "backend"),
            ("Auth Adapter", self.root_dir / "adapters" / "auth"),
            ("Pagopar Adapter", self.root_dir / "adapters" / "pagopar"),
            ("Stripe Adapter", self.root_dir / "adapters" / "stripe"),
            ("Storage Adapter", self.root_dir / "adapters" / "storage"),
            ("SIFEN Adapter", self.root_dir / "adapters" / "sifen"),
        ]

        for service_name, service_dir in services:
            if not service_dir.exists():
                continue
            has_health = False
            for py_file in service_dir.rglob("*.py"):
                if self.is_ignored_path(py_file):
                    continue
                try:
                    text = py_file.read_text(encoding="utf-8", errors="replace")
                    if (
                        "/health" in text
                        or "health_router" in text
                        or "/ready" in text
                        or "healthz" in text
                    ):
                        has_health = True
                        break
                except Exception:
                    pass

            if not has_health:
                self.add_violation(
                    "REQUIRE_HEALTHCHECKS",
                    "BLOCKER",
                    service_dir,
                    1,
                    f"Observability Violation: {service_name} lacks /health or /ready endpoint.",
                )


def format_console_report(stats: AuditStats) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("🛡️  GATEKEEPER ZERO-MOCK & ARCHITECTURE AUDIT REPORT")
    lines.append("=" * 80)
    lines.append(f"Total Python Files Scanned: {stats.total_files_scanned}")
    lines.append(f"  - Production Files:       {stats.production_files_scanned}")
    lines.append(f"  - Test Files:             {stats.test_files_scanned}")
    lines.append(f"Blocker Violations:         {stats.blocker_count}")
    lines.append(f"Warnings:                   {stats.warning_count}")
    lines.append("-" * 80)

    if not stats.violations:
        lines.append("✅ ALL CHECKS PASSED: Codebase strictly complies with Zero Mock Doktrin")
        lines.append("   and software-testing-audit requirements.")
        lines.append("=" * 80)
        return "\n".join(lines)

    for v in stats.violations:
        prefix = "❌ [BLOCKER]" if v.severity == "BLOCKER" else "⚠️  [WARNING]"
        lines.append(f"{prefix} {v.rule_id} at {v.file_path}:{v.line_number}")
        lines.append(f"   Message: {v.message}")
        if v.code_snippet:
            lines.append(f"   Code:    {v.code_snippet}")
        lines.append("")

    lines.append("=" * 80)
    if stats.blocker_count > 0:
        lines.append(
            f"❌ AUDIT FAILED: {stats.blocker_count} blocker violation(s) must be resolved."
        )
    else:
        lines.append("⚠️  AUDIT PASSED WITH WARNINGS (no blockers).")
    lines.append("=" * 80)
    return "\n".join(lines)


def write_github_step_summary(stats: AuditStats) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    status_icon = "✅" if stats.blocker_count == 0 else "❌"
    status_text = "PASSED" if stats.blocker_count == 0 else "FAILED"

    md = []
    md.append(f"## {status_icon} Gatekeeper Zero-Mock & Architecture Audit: {status_text}\n")
    md.append(
        "Automated verification under **Zero Mock Doktrin** and **software-testing-audit**.\n"
    )

    md.append("| Metric | Count |")
    md.append("|---|---|")
    md.append(f"| Total Files Scanned | {stats.total_files_scanned} |")
    md.append(f"| Production Files | {stats.production_files_scanned} |")
    md.append(f"| Test Files | {stats.test_files_scanned} |")
    md.append(f"| **Blocker Violations** | **{stats.blocker_count}** |")
    md.append(f"| Warnings | {stats.warning_count} |\n")

    if stats.violations:
        md.append("### 🔍 Audit Findings\n")
        md.append("| Severity | Rule | Location | Description |")
        md.append("|---|---|---|---|")
        for v in stats.violations:
            badge = "🔴 BLOCKER" if v.severity == "BLOCKER" else "🟡 WARNING"
            loc = f"`{v.file_path}:{v.line_number}`"
            msg = v.message.replace("|", "\\|")
            md.append(f"| {badge} | `{v.rule_id}` | {loc} | {msg} |")
        md.append("")

    if stats.blocker_count == 0:
        md.append(
            "> **Gatekeeper Recommendation**: CI verification succeeded. "
            "Ready for architectural evaluation and merge approval.\n"
        )
    else:
        md.append(
            "> **Gatekeeper Recommendation**: PR blocked. "
            "Resolve the blocker violations above before requesting review.\n"
        )

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
    except Exception as e:
        print(f"Warning: Failed to write to GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit codebase for Zero Mock Doktrin and architecture compliance."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("."),
        help="Path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--github-summary",
        action="store_true",
        help="Write summary to $GITHUB_STEP_SUMMARY if available",
    )
    args = parser.parse_args()

    auditor = ZeroMockAuditor(args.path)
    stats = auditor.scan_all()

    report = format_console_report(stats)
    print(report)

    if args.github_summary or os.environ.get("GITHUB_STEP_SUMMARY"):
        write_github_step_summary(stats)

    return 1 if stats.blocker_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
