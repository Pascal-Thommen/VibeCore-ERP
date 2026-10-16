"""
Tests for Zero-Mock & Architecture Audit Tool (scripts/audit_zero_mock.py).

Validates that:
- Production mock imports are detected as BLOCKER
- Bypass flags are detected as BLOCKER
- Empty dummy stubs are detected as BLOCKER
- Scheintests with no assertions are detected as BLOCKER
- Core Invariance violations are detected as BLOCKER
- Adapter Isolation violations are detected as BLOCKER
- Valid production and test code passes cleanly
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_zero_mock import ZeroMockAuditor  # noqa: E402


def test_clean_directory_passes(tmp_path: Path) -> None:
    prod_file = tmp_path / "service.py"
    prod_file.write_text(
        "def calculate_vat(amount: float) -> float:\n"
        "    vat_rate = 0.10\n"
        "    return round(amount * vat_rate, 2)\n"
    )

    test_file = tmp_path / "tests" / "test_service.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "from service import calculate_vat\n\n"
        "def test_calculate_vat():\n"
        "    assert calculate_vat(100.0) == 10.0\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    assert stats.blocker_count == 0


def test_production_mock_import_detected(tmp_path: Path) -> None:
    prod_file = tmp_path / "backend" / "app" / "service.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text(
        "from unittest.mock import MagicMock\n\n"
        "def get_user():\n"
        "    return MagicMock()\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_PROD_MOCKS"]
    assert len(blockers) >= 1
    assert any("forbidden mock" in b.message.lower() for b in blockers)


def test_bypass_flags_detected(tmp_path: Path) -> None:
    prod_file = tmp_path / "app" / "config.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text(
        "SKIP_AUTH = True\n"
        "MOCK_MODE = True\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_MOCK_FLAGS"]
    assert len(blockers) == 2


def test_empty_stubs_detected(tmp_path: Path) -> None:
    prod_file = tmp_path / "app" / "orders.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text(
        "def create_order(order_data):\n"
        "    pass\n\n"
        "def cancel_order(order_id):\n"
        "    raise NotImplementedError('TODO')\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_EMPTY_STUBS"]
    assert len(blockers) == 2


def test_scheintest_without_assertions_detected(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_fake.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "def test_dummy_behavior():\n"
        "    pass\n\n"
        "def test_second_dummy():\n"
        "    x = 1 + 1\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_SCHEINTESTS"]
    assert len(blockers) == 2


def test_core_invariance_violation_detected(tmp_path: Path) -> None:
    core_file = tmp_path / "backend" / "app" / "core" / "journal.py"
    core_file.parent.mkdir(parents=True, exist_ok=True)
    core_file.write_text(
        "from adapters.pagopar import PagoparClient\n\n"
        "def post_journal():\n"
        "    pass\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "CORE_INVARIANCE"]
    assert len(blockers) >= 1


def test_adapter_isolation_violation_detected(tmp_path: Path) -> None:
    adapter_file = tmp_path / "adapters" / "stripe" / "app" / "service.py"
    adapter_file.parent.mkdir(parents=True, exist_ok=True)
    adapter_file.write_text(
        "from app.db.base import get_session\n\n"
        "def charge():\n"
        "    return None\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "ADAPTER_ISOLATION"]
    assert len(blockers) >= 1
