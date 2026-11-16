#!/usr/bin/env python3
"""Idempotent Demo Data Seed & Verification Script for Dolibarr ERP (Oro Ku'i)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_MCP_DIR = _SCRIPT_DIR.parent / "mcp"
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from dolibarr_mcp.client import (  # noqa: E402
    DEFAULT_DOLIBARR_API_KEY,
    DEFAULT_DOLIBARR_API_URL,
    DEFAULT_TIMEOUT_SECONDS,
    DolibarrClient,
    DolibarrError,
)


def run_container_php_seeder(container_name: str = "vibecore-dolibarr-web") -> dict[str, Any]:
    """Execute the idempotent PHP seeder inside the running Dolibarr container."""
    php_script = _SCRIPT_DIR / "before-starting.d" / "20-seed-orokui-demodata.php"
    if not php_script.exists():
        return {"executed": False, "reason": f"Script not found: {php_script}"}

    content = php_script.read_bytes()
    proc = subprocess.run(
        ["docker", "exec", "-i", container_name, "php"],
        input=content,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return {
        "executed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", errors="replace").strip(),
        "stderr": proc.stderr.decode("utf-8", errors="replace").strip(),
    }


def verify_demodata(client: DolibarrClient) -> dict[str, Any]:
    """Verify that all active Dolibarr modules contain complete demo data."""
    summary = client.get_erp_summary()
    counts = summary["counts"]
    minimums = {
        "customers": 5,
        "suppliers": 3,
        "contacts": 6,
        "products_and_services": 9,
        "warehouses": 3,
        "stock_movements": 16,
        "proposals": 3,
        "customer_orders": 3,
        "customer_invoices_total": 6,
        "pos_receipts": 2,
        "supplier_orders": 1,
        "supplier_invoices": 2,
        "bank_and_cash_accounts": 2,
        "boms": 1,
        "manufacturing_orders": 1,
    }
    missing = {
        key: {"actual": counts.get(key, 0), "expected_min": expected}
        for key, expected in minimums.items()
        if int(counts.get(key, 0)) < expected
    }
    return {
        "ok": len(missing) == 0,
        "summary": summary,
        "missing_requirements": missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed and verify Oro Ku'i Dolibarr ERP demo data."
    )
    parser.add_argument("--api-url", default=DEFAULT_DOLIBARR_API_URL)
    parser.add_argument("--api-key", default=DEFAULT_DOLIBARR_API_KEY)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)

    client = DolibarrClient(
        base_url=args.api_url,
        api_key=args.api_key,
        timeout=args.timeout,
    )

    try:
        seed_result = None
        if not args.verify_only:
            seed_result = run_container_php_seeder()
        verification = verify_demodata(client)
        output = {
            "ok": verification["ok"],
            "seeder": seed_result,
            "verification": verification,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0 if verification["ok"] else 1
    except DolibarrError as exc:
        print(json.dumps(exc.to_dict(), indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
