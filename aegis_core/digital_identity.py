"""Owner-controlled digital identity and companion-session policy for Aegis."""

from __future__ import annotations

from typing import Any

from aegis_core.store import AegisStore


class DigitalIdentityService:
    """Exposes identity presentation without allowing identity to expand authority."""

    def __init__(self, store: AegisStore) -> None:
        self.store = store

    def status(self) -> dict[str, Any]:
        return {
            "profile": self.store.get_identity_profile(),
            "assets": self.store.list_identity_assets(),
            "companion_sessions": self.store.list_companion_sessions(),
            "modes": {
                "executive": "Private owner-facing business partner presentation.",
                "study": "Shared learning, explanation, practice, and review presentation.",
                "studio": "Public content and video presentation with explicit AI disclosure.",
                "public_incognito": "Neutral public presentation with owner and project identifiers removed.",
                "private_incognito": "Local-only ephemeral session with metadata-only audit and no learning retention.",
            },
            "screen_companion": {
                "available": True,
                "capture_boundary": "browser_permission_each_session",
                "frame_destination": "loopback_in_memory_on_owner_click",
                "recording": False,
                "automatic_visual_analysis": False,
                "raw_frame_retention": "none",
                "notes": "owner_controlled_single_frame",
            },
            "production_readiness": {
                "portrait": "active",
                "full_body_master": "reference_ready",
                "motion_preview": "active_browser_animation",
                "motion_rig": "renderer_not_installed",
                "lip_sync": "requires_layered_or_renderer_asset",
                "public_identity_accounts": "not_connected",
            },
        }

    def model_context(self) -> dict[str, Any]:
        profile = self.store.get_identity_profile()
        return {
            "name": profile["display_name"],
            "role": profile["role_title"],
            "pronouns": profile["pronouns"],
            "embodiment": profile["embodiment"],
            "conversation_style": profile["conversation_style"],
            "presentation_mode": profile["presentation_mode"],
            "traits": profile["traits"],
            "truth_standard": profile["truth_standard"],
            "authority_model": profile["authority_model"],
            "disclosure": profile["identity_disclosure"],
        }
