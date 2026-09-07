"""Operator authentication for sensitive API routes (SEC-01…03)."""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException


OPERATOR_HEADER = "X-Operator-Key"


def get_operator_api_key() -> str:
    return (os.getenv("OPERATOR_API_KEY") or "").strip()


def require_operator_key(
    x_operator_key: Optional[str] = Header(default=None, alias=OPERATOR_HEADER),
) -> None:
    """
    Require X-Operator-Key matching OPERATOR_API_KEY.
    Fail closed when the env key is unset (approvals / last-result must not be open).
    """
    expected = get_operator_api_key()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="OPERATOR_API_KEY is not configured on the server",
        )
    provided = (x_operator_key or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Operator-Key",
        )
