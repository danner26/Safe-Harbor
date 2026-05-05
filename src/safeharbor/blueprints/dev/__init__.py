"""Dev-only blueprint package (gated to non-production)."""

from __future__ import annotations

from safeharbor.blueprints.dev.views import dev_bp

__all__ = ["dev_bp"]
