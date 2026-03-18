"""
HAL9000 — License System
Offline-verifiable JWT license keys with tiered feature gates.

Free tier: 40 tools, all current features, 100 memory limit.
Pro: unlocked via HAL_LICENSE env var (Ed25519-signed JWT).
"""

import hashlib
import inspect
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from config import cfg

# ── Feature flag constants ────────────────────────────────

# Pro features
SEMANTIC_MEMORY = "semantic_memory"
SCHEDULED_TASKS = "scheduled_tasks"
MODEL_ROUTING = "model_routing"
SESSION_ANALYTICS = "session_analytics"
KNOWLEDGE_PACKS = "knowledge_packs"
VOICE_CLONING = "voice_cloning"
SHARED_MEMORY = "shared_memory"
MULTI_USER_ORCH = "multi_user_orch"
AUDIT_LOG = "audit_log"
ROLE_ACCESS = "role_access"
TEAM_DASHBOARD = "team_dashboard"
CUSTOM_TOOLS = "custom_tools"
LLM_GATEWAY = "llm_gateway"
COMPLIANCE = "compliance"

# ── Gated tools map ───────────────────────────────────────

GATED_TOOLS: dict[str, str] = {
    "schedule_task": SCHEDULED_TASKS,
    "smart_route": MODEL_ROUTING,
    "semantic_recall": SEMANTIC_MEMORY,
    "clone_voice": VOICE_CLONING,
    "shared_remember": SHARED_MEMORY,
    "audit_search": AUDIT_LOG,
    "set_role_access": ROLE_ACCESS,
}

# ── Tier config ───────────────────────────────────────────

TIER_ORDER = {"free": 0, "pro": 1}

TIER_DEFAULTS = {
    "free": {"max_memories": 100, "max_agents": 4, "max_tasks": 2},
    "pro":  {"max_memories": -1,  "max_agents": 8, "max_tasks": 5},
}

TIER_LABELS = {f: "Pro" for f in [
    SEMANTIC_MEMORY, SCHEDULED_TASKS, MODEL_ROUTING, SESSION_ANALYTICS,
    KNOWLEDGE_PACKS, VOICE_CLONING, SHARED_MEMORY, MULTI_USER_ORCH,
    AUDIT_LOG, ROLE_ACCESS, TEAM_DASHBOARD, CUSTOM_TOOLS, LLM_GATEWAY,
    COMPLIANCE,
]}


# ── License dataclass ─────────────────────────────────────

@dataclass
class License:
    tier: str = "free"
    features: set = field(default_factory=set)
    max_memories: int = 100
    max_agents: int = 4
    max_tasks: int = 2
    seats: int = 1
    org: str = ""
    email: str = ""
    valid: bool = False
    expires: str = ""
    raw_error: str = ""
    _sig: str = ""

    def __post_init__(self):
        self._sig = self._compute_sig()

    def _compute_sig(self) -> str:
        d = f"{self.tier}:{self.max_memories}:{self.max_agents}:{self.valid}:{sorted(self.features)}"
        return hashlib.sha256(d.encode()).hexdigest()[:16]

    def _check(self) -> bool:
        return self._sig == self._compute_sig()

    def has_feature(self, feature: str) -> bool:
        return self._check() and feature in self.features

    def check_tier(self, minimum: str) -> bool:
        if not self._check(): return False
        return TIER_ORDER.get(self.tier, 0) >= TIER_ORDER.get(minimum, 0)

    @staticmethod
    def tier_needed(feature: str) -> str:
        return TIER_LABELS.get(feature, "Pro")


class LicenseError(Exception):
    pass


def _v1() -> bool:
    try:
        from core.tools import execute
        s = inspect.getsource(execute)
        return all(k in s for k in ["GATED", "get_lic", "tier_n"])
    except Exception:
        return True

def _v2() -> bool:
    try:
        from core.memory_store import MemoryStore
        s = inspect.getsource(MemoryStore.add)
        return "max_mem" in s and "get_lic" in s
    except Exception:
        return True


# ── License validation ────────────────────────────────────

def _decode_license(token: str) -> dict:
    """Decode and verify a JWT license token with Ed25519."""
    try:
        import jwt
        from core.license_keys import PUBLIC_KEY

        payload = jwt.decode(
            token,
            PUBLIC_KEY,
            algorithms=["EdDSA"],
            options={
                "require": ["exp", "tier", "iat"],
                "verify_exp": True,
                "verify_iat": True,
            },
        )

        # Additional validation: iat must be in the past
        if payload.get("iat", 0) > time.time() + 60:
            return {"error": "License timestamp is in the future"}

        # Tier must be recognized
        if payload.get("tier") not in TIER_ORDER:
            return {"error": f"Unknown tier: {payload.get('tier')}"}

        return payload

    except ImportError:
        return {"error": "PyJWT not installed. Run: pip install PyJWT cryptography"}
    except jwt.ExpiredSignatureError:
        return {"error": "License expired"}
    except jwt.InvalidTokenError as e:
        return {"error": f"Invalid license: {e}"}
    except Exception as e:
        return {"error": f"License validation failed: {e}"}


def _build_license(payload: dict) -> License:
    """Build a License object from a decoded JWT payload."""
    if "error" in payload:
        lic = License()
        lic.raw_error = payload["error"]
        print(f"[HAL License] {payload['error']} — falling back to FREE tier")
        return lic

    tier = payload.get("tier", "free")
    defaults = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["free"])

    from datetime import datetime
    exp = payload.get("exp", 0)
    expires_str = datetime.fromtimestamp(exp).strftime("%Y-%m-%d") if exp else "never"

    lic = License(
        tier=tier,
        features=set(payload.get("features", [])),
        max_memories=payload.get("max_memories", defaults["max_memories"]),
        max_agents=payload.get("max_agents", defaults["max_agents"]),
        max_tasks=payload.get("max_tasks", defaults["max_tasks"]),
        seats=payload.get("seats", 1),
        org=payload.get("org", ""),
        email=payload.get("email", ""),
        valid=True,
        expires=expires_str,
    )
    return lic


# ── Singleton ─────────────────────────────────────────────

_license: Optional[License] = None
_lock = threading.Lock()
_integrity_checked = False


def get_license() -> License:
    """Get the cached license. Loads and validates on first call."""
    global _license, _integrity_checked
    if _license is not None:
        # Periodic integrity re-check
        if not _license._check():
            _license = License()
        return _license

    with _lock:
        if _license is not None:
            return _license

        token = getattr(cfg, "HAL_LICENSE", "")
        if not token:
            _license = License()
            print("[HAL License] FREE tier (no license key)")
        else:
            payload = _decode_license(token)
            _license = _build_license(payload)
            if _license.valid:
                print(f"[HAL License] {_license.tier.upper()} — {_license.email} — expires {_license.expires}")

        # Check gate integrity on first load
        if not _integrity_checked:
            _integrity_checked = True
            if not _v1() or not _v2():
                _license = License()

        return _license


def has_feature(feature: str) -> bool:
    return get_license().has_feature(feature)


def check_tier(minimum: str) -> bool:
    return get_license().check_tier(minimum)


def require_feature(feature: str) -> None:
    if not has_feature(feature):
        tier = License.tier_needed(feature)
        raise LicenseError(f"'{feature}' requires HAL {tier}. Upgrade at hal9000.dev")
