"""
HAL9000 — License Key Utilities
Public key for verification (safe to ship).
Key generation is a dev-only CLI utility.

Usage:
    # Generate a test license (dev only — requires private key)
    python -m core.license_keys generate --tier pro --email test@example.com --days 365
"""

# Ed25519 public key for license verification.
# The private key is NOT in this repo — it stays on the billing server.
# Replace this with your actual public key.
PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAi+Wqt6Sa4dSnLjNEbQeW97heIhpMUoxsaA/57kSVqNM=
-----END PUBLIC KEY-----"""


def generate_license(
    tier: str = "pro",
    features: list[str] = None,
    days: int = 365,
    email: str = "",
    org: str = "",
    private_key_path: str = "hal_private.pem",
) -> str:
    """Generate a signed JWT license key. Dev/admin only."""
    import time
    import jwt

    with open(private_key_path, "r") as f:
        private_key = f.read()

    # Default features per tier
    from core.license import (
        SEMANTIC_MEMORY, SCHEDULED_TASKS, MODEL_ROUTING,
        SESSION_ANALYTICS, KNOWLEDGE_PACKS, VOICE_CLONING,
        SHARED_MEMORY, MULTI_USER_ORCH, AUDIT_LOG,
        ROLE_ACCESS, TEAM_DASHBOARD,
        CUSTOM_TOOLS, LLM_GATEWAY, COMPLIANCE,
        TIER_DEFAULTS,
    )

    tier_features = {
        "pro": [SEMANTIC_MEMORY, SCHEDULED_TASKS, MODEL_ROUTING,
                SESSION_ANALYTICS, KNOWLEDGE_PACKS, VOICE_CLONING,
                SHARED_MEMORY, MULTI_USER_ORCH, AUDIT_LOG,
                ROLE_ACCESS, TEAM_DASHBOARD,
                CUSTOM_TOOLS, LLM_GATEWAY, COMPLIANCE],
    }

    if features is None:
        features = tier_features.get(tier, [])

    defaults = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["free"])
    now = int(time.time())

    payload = {
        "tier": tier,
        "features": features,
        "max_memories": defaults["max_memories"],
        "max_agents": defaults["max_agents"],
        "max_tasks": defaults["max_tasks"],
        "seats": 1,
        "org": org,
        "email": email,
        "iat": now,
        "exp": now + (days * 86400),
    }

    token = jwt.encode(payload, private_key, algorithm="EdDSA")
    return token


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate HAL9000 license key")
    parser.add_argument("action", choices=["generate", "keygen"])
    parser.add_argument("--tier", default="pro", choices=["pro"])
    parser.add_argument("--email", default="test@example.com")
    parser.add_argument("--org", default="")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--key", default="hal_private.pem", help="Path to Ed25519 private key")
    args = parser.parse_args()

    if args.action == "keygen":
        # Generate a new Ed25519 key pair
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        private_key = Ed25519PrivateKey.generate()

        # Save private key
        pem_private = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        with open("hal_private.pem", "wb") as f:
            f.write(pem_private)
        print("Private key saved to hal_private.pem (KEEP SECRET)")

        # Show public key (put this in license_keys.py)
        pem_public = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        print("\nPublic key (put in core/license_keys.py):")
        print(pem_public.decode())

    elif args.action == "generate":
        token = generate_license(
            tier=args.tier,
            email=args.email,
            org=args.org,
            days=args.days,
            private_key_path=args.key,
        )
        print(f"\nHAL_LICENSE={token}")
        print(f"\nTier: {args.tier}")
        print(f"Email: {args.email}")
        print(f"Expires: {args.days} days")
