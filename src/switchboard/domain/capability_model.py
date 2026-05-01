# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""CapabilityModel — describes what a downstream model can do.

Section 8.4
"""

from __future__ import annotations

from pydantic import BaseModel


class CapabilityModel(BaseModel):
    """Capabilities and metadata for a single downstream model.

    Attributes:
        name:  Model identifier string (e.g. ``"gpt-4o-mini"``).
    """

    name: str = ""
