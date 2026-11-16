#!/usr/bin/env python3
"""Entry point for the local Dolibarr ERP MCP Server (Oro Ku'i / UPA Extension)."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure local package import works even without prior pip installation
_MCP_DIR = Path(__file__).resolve().parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from dolibarr_mcp.server import main, mcp  # noqa: E402

__all__ = ["main", "mcp"]

if __name__ == "__main__":
    sys.exit(main())
