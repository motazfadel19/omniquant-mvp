#!/usr/bin/env python
"""
One-command local setup.

Why this exists
---------------
`AUTH_TOKEN` is a shared secret: the backend compares it on every write request
and the frontend sends it. Copying a *public* value out of `.env.example`
defeats the whole point — anyone who has read your repository knows it, and the
"refuse to boot in live mode with the default token" guard can no longer tell
the difference between "configured" and "still the sample value".

So the examples ship EMPTY (which fails closed: every write returns 503 until
configured) and this script generates a real random secret and writes it into
both files.

    python backend/tools/setup_env.py            # create / fill missing values
    python backend/tools/setup_env.py --force    # rotate the token
    python backend/tools/setup_env.py --print    # show the current token
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = ROOT / "backend" / ".env"
FRONTEND_ENV = ROOT / "frontend" / ".env.local"
BACKEND_EXAMPLE = ROOT / "backend" / ".env.example"
FRONTEND_EXAMPLE = ROOT / "frontend" / ".env.example"

PLACEHOLDERS = {
    "", "change-me", "dev-local-token-change-me", "changeme", "secret",
    "omniquant-local-dev-token", "your-token-here", "token",
}
MIN_LENGTH = 24


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def write_env(path: Path, example: Path, values: dict[str, str]) -> None:
    """Write `values`, preserving the comments and ordering of the example."""
    if example.exists():
        lines = example.read_text(encoding="utf-8").splitlines()
    else:
        lines = [f"{k}={v}" for k, v in values.items()]

    out = []
    seen: set[str] = set()
    for line in lines:
        key = line.split("=")[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key and key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in values.items():
        if key not in seen:
            out.append(f"{key}={val}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a local AUTH_TOKEN for OmniQuant.")
    ap.add_argument("--force", action="store_true", help="rotate the token even if one exists")
    ap.add_argument("--print", dest="do_print", action="store_true",
                    help="print the current token and exit")
    args = ap.parse_args(argv)

    backend_values = read_env(BACKEND_ENV) or read_env(BACKEND_EXAMPLE)
    frontend_values = read_env(FRONTEND_ENV) or read_env(FRONTEND_EXAMPLE)

    current = backend_values.get("AUTH_TOKEN", "")
    configured = current not in PLACEHOLDERS and len(current) >= MIN_LENGTH

    if args.do_print:
        print(current or "(not configured)")
        return 0

    if configured and not args.force:
        print(f"[=] AUTH_TOKEN already configured ({len(current)} chars).")
        print("    Use --force to rotate it.")
        if backend_values.get("AUTH_TOKEN") != frontend_values.get("NEXT_PUBLIC_AUTH_TOKEN"):
            print("[!] frontend/backend tokens differ — syncing frontend to the backend value.")
            frontend_values["NEXT_PUBLIC_AUTH_TOKEN"] = current
            write_env(FRONTEND_ENV, FRONTEND_EXAMPLE, frontend_values)
            print(f"[OK] wrote {FRONTEND_ENV}")
        return 0

    token = generate_token()
    backend_values["AUTH_TOKEN"] = token
    frontend_values["NEXT_PUBLIC_AUTH_TOKEN"] = token

    write_env(BACKEND_ENV, BACKEND_EXAMPLE, backend_values)
    write_env(FRONTEND_ENV, FRONTEND_EXAMPLE, frontend_values)

    print("=" * 62)
    print("  Generated a fresh AUTH_TOKEN (secrets.token_urlsafe(32))")
    print("=" * 62)
    print(f"  backend/.env         AUTH_TOKEN={token}")
    print(f"  frontend/.env.local  NEXT_PUBLIC_AUTH_TOKEN={token}")
    print()
    print("  Both files are git-ignored. Never commit them.")
    print("  Restart the backend, and restart `npm run dev` (NEXT_PUBLIC_*")
    print("  variables are baked in at build time).")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
