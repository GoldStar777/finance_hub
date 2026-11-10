import os
import sys
import errno
import shutil
import socket
import subprocess
from pathlib import Path
import uvicorn

try:
    from app.config import DEFAULT_PORT
except ValueError as exc:
    print(f"[ERROR] {exc}", file=sys.stderr)
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

def ensure_port_available(host: str, port: int) -> None:
    """Refuse a duplicate launch before doing any startup work."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        result = probe.connect_ex((host, port))
        if result == 0:
            raise RuntimeError(
                f"Finance Hub cannot start: {host}:{port} is already in use. "
                "The existing service has been left untouched."
            )
        if result != errno.ECONNREFUSED:
            # ECONNREFUSED is the expected response when no listener owns the port.
            # Any other result means we cannot safely rule out a conflicting service.
            raise RuntimeError(
                f"Finance Hub cannot verify whether {host}:{port} is free "
                f"(socket error {result}); startup stopped without changing the existing service."
            )

def ensure_frontend_built():
    """Builds the frontend if dist does not exist."""
    if not FRONTEND_DIST.exists():
        if not (FRONTEND_DIR / "node_modules").exists():
            raise RuntimeError(
                "Frontend bundle (frontend/dist) and dependencies (frontend/node_modules) are missing. "
                "Run `./scripts/install.sh` (or `cd frontend && npm ci && npm run build`) first."
            )
        print("[INFO] Building frontend assets (one-time build)...")
        npm_cmd = shutil.which("npm")
        if not npm_cmd:
            for candidate in ("/opt/homebrew/bin/npm", "/usr/local/bin/npm"):
                if Path(candidate).exists():
                    npm_cmd = candidate
                    break
        if not npm_cmd:
            raise FileNotFoundError("npm executable not found on PATH; build frontend manually with `cd frontend && npm run build`.")
        subprocess.run([npm_cmd, "run", "build"], cwd=str(FRONTEND_DIR), check=True)
        print("[INFO] Frontend build completed successfully.\n")

if __name__ == "__main__":
    port = DEFAULT_PORT
    try:
        ensure_port_available("127.0.0.1", port)
        ensure_frontend_built()
    except (RuntimeError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"\n=======================================================")
    print(f"  Finance Hub v2.0")
    print(f"  Local Dashboard:  http://127.0.0.1:{port}")
    print(f"  API Docs (OpenAPI): http://127.0.0.1:{port}/docs")
    print(f"=======================================================\n")
    print("  Frontend source changes require `npm run build` in frontend/.")
    print("  Restart Finance Hub (or its background service, if installed) after building or changing code.")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
