import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_visible_files() -> list[Path]:
    """Lists all workspace files respecting .gitignore, both in Git checkouts and .git-less snapshots."""
    if (REPO_ROOT / ".git").exists():
        res = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=True,
        )
    else:
        with tempfile.TemporaryDirectory() as tmp_git:
            subprocess.run(["git", "init", "--bare", tmp_git], capture_output=True, check=True)
            res = subprocess.run(
                [
                    "git",
                    f"--git-dir={tmp_git}",
                    f"--work-tree={REPO_ROOT}",
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                capture_output=True,
                check=True,
            )
    rel_paths = [p for p in res.stdout.decode("utf-8", errors="ignore").split("\x00") if p]
    return [REPO_ROOT / rel for rel in rel_paths if (REPO_ROOT / rel).is_file()]


def _run_git_check_ignore(args: list[str], input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Runs `git check-ignore --no-index` against REPO_ROOT using an isolated bare git-dir if .git is absent."""
    if (REPO_ROOT / ".git").exists():
        return subprocess.run(
            ["git", "check-ignore", "--no-index", *args],
            cwd=str(REPO_ROOT),
            input=input_text,
            text=True,
            capture_output=True,
            check=check,
        )
    with tempfile.TemporaryDirectory() as tmp_git:
        subprocess.run(["git", "init", "--bare", tmp_git], capture_output=True, check=True)
        return subprocess.run(
            ["git", f"--git-dir={tmp_git}", f"--work-tree={REPO_ROOT}", "check-ignore", "--no-index", *args],
            input=input_text,
            text=True,
            capture_output=True,
            check=check,
        )


def _make_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IRUSR | stat.S_IXGRP | stat.S_IXOTH)


def _setup_isolated_sandbox(tmp_path: Path, platform_name: str) -> tuple[Path, Path, dict[str, str]]:
    """
    Creates an isolated sandbox copy of install/uninstall scripts with fake CLI shims,
    pre-populated ./data sentinel files, and an isolated HOME/XDG_CONFIG_HOME.
    Never modifies the real workspace or host environment.
    """
    sandbox_proj = tmp_path / "sandbox_finance_hub"
    (sandbox_proj / "scripts").mkdir(parents=True)
    (sandbox_proj / "frontend").mkdir(parents=True)
    (sandbox_proj / "data" / "receipts").mkdir(parents=True)
    (sandbox_proj / "data" / "backups").mkdir(parents=True)
    (sandbox_proj / "data" / "profiles" / "shared").mkdir(parents=True)

    for script_name in ("install.sh", "uninstall.sh"):
        dst = sandbox_proj / "scripts" / script_name
        shutil.copy2(REPO_ROOT / "scripts" / script_name, dst)
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR)

    (sandbox_proj / "requirements.txt").write_text("fastapi==0.156.3\n", encoding="utf-8")
    (sandbox_proj / "run.py").write_text("# stub runner\n", encoding="utf-8")
    (sandbox_proj / ".env.example").write_text("APP_PORT=8050\nBASE_CURRENCY=GBP\n", encoding="utf-8")
    (sandbox_proj / ".env").write_text("APP_PORT=8077\n", encoding="utf-8")
    (sandbox_proj / "frontend" / "package.json").write_text('{"name":"test","version":"1.0.0"}\n', encoding="utf-8")
    (sandbox_proj / "frontend" / "package-lock.json").write_text('{"name":"test","lockfileVersion":3}\n', encoding="utf-8")

    # Sentinel financial data that MUST survive installs, upgrades, and default uninstalls
    (sandbox_proj / "data" / "finances.db").write_bytes(b"SQLite-sentinel-default")
    (sandbox_proj / "data" / "profiles" / "shared" / "finances.db").write_bytes(b"SQLite-sentinel-profile")
    (sandbox_proj / "data" / "receipts" / "sample_receipt.jpg").write_bytes(b"receipt-sentinel")
    (sandbox_proj / "data" / "backups" / "backup_sentinel.zip").write_bytes(b"zip-sentinel")

    fake_home = tmp_path / "fake_home"
    fake_xdg = tmp_path / "fake_xdg"
    fake_home.mkdir()
    fake_xdg.mkdir()

    fake_bin = tmp_path / "fake_bin"
    fake_bin.mkdir()
    service_log = tmp_path / "service_calls.log"

    _make_executable(
        fake_bin / "uname",
        f"#!/bin/sh\nif [ \"$1\" = \"-s\" ] || [ $# -eq 0 ]; then echo '{platform_name}'; else /usr/bin/uname \"$@\"; fi\n",
    )
    _make_executable(
        fake_bin / "node",
        "#!/bin/sh\nif [ \"$1\" = \"-v\" ]; then echo 'v22.0.0'; else exit 0; fi\n",
    )
    _make_executable(
        fake_bin / "npm",
        (
            "#!/bin/sh\n"
            f"echo \"npm $*\" >> '{service_log}'\n"
            "if [ \"$1\" = \"ci\" ] || [ \"$1\" = \"install\" ]; then mkdir -p node_modules; fi\n"
            "if [ \"$1\" = \"run\" ] && [ \"$2\" = \"build\" ]; then mkdir -p dist && touch dist/index.html; fi\n"
        ),
    )
    _make_executable(
        fake_bin / "python3",
        (
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-c\" ]; then exit 0; fi\n"
            "if [ \"$1\" = \"-m\" ] && [ \"$2\" = \"venv\" ]; then\n"
            "  TARGET=\"$3\"\n"
            "  mkdir -p \"$TARGET/bin\"\n"
            "  cat > \"$TARGET/bin/python\" <<'PYEOF'\n"
            "#!/bin/sh\n"
            f"echo \"venv-python $*\" >> '{service_log}'\n"
            "exit 0\n"
            "PYEOF\n"
            "  chmod +x \"$TARGET/bin/python\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n"
        ),
    )
    _make_executable(
        fake_bin / "launchctl",
        f"#!/bin/sh\necho \"launchctl $*\" >> '{service_log}'\nexit 0\n",
    )
    _make_executable(
        fake_bin / "systemctl",
        f"#!/bin/sh\necho \"systemctl $*\" >> '{service_log}'\nexit 0\n",
    )

    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HOME": str(fake_home),
        "XDG_CONFIG_HOME": str(fake_xdg),
    }
    return sandbox_proj, service_log, env


def test_no_sensitive_files_hardcoded_paths_or_secrets_in_repo():
    files = _git_visible_files()
    forbidden_patterns = [
        ("macOS user home path", re.compile(r"/Users/[A-Za-z0-9_.-]+")),
        ("Linux user home path", re.compile(r"/home/[A-Za-z0-9_.-]+")),
        ("Windows user home path", re.compile(r"C:\\\\Users\\\\[A-Za-z0-9_.-]+")),
        ("Personal service label", re.compile(r"com\.(?!financehub\b)[A-Za-z0-9_-]+\.financehub")),
        ("Private key header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
        ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
        ("API secret token", re.compile(r"\bsk-(?:proj-|live-)?[A-Za-z0-9]{20,}\b")),
        (
            "Personal email address",
            re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.(?:com|org|net)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        ),
    ]
    forbidden_rel_extensions = {".db", ".sqlite", ".sqlite3", ".zip", ".plist", ".service", ".log"}

    violations: list[str] = []
    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == "tests/test_public_readiness.py":
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            violations.append(f"Tracked/unignored env file: {rel}")
        if path.suffix.lower() in forbidden_rel_extensions:
            violations.append(f"Tracked/unignored runtime/binary extension: {rel}")
        if rel.startswith("data/"):
            violations.append(f"Tracked/unignored data/ path: {rel}")

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, pat in forbidden_patterns:
                if pat.search(line):
                    violations.append(f"{rel}:{lineno} matched {label}")

    assert not violations, "Privacy/readiness violations found:\n" + "\n".join(violations)


def test_gitignore_excludes_sensitive_and_local_paths():
    sample_ignored = [
        "data/",
        "data/finances.db",
        "data/finances.db-wal",
        "data/finances.db-shm",
        "data/profiles/default/finances.db",
        "data/backups/finance_hub_backup_20261110.zip",
        "data/receipts/receipt.jpg",
        "backup.zip",
        ".env",
        ".env.local",
        "com.financehub.app.plist",
        "financehub.service",
        "app.log",
        "venv/",
        ".venv/",
        "frontend/node_modules/",
        "frontend/dist/",
        "finances.db.safety_backup_1",
    ]
    res = _run_git_check_ignore(["--stdin"], input_text="\n".join(sample_ignored) + "\n", check=True)
    ignored = set(res.stdout.splitlines())
    for item in sample_ignored:
        assert item in ignored, f".gitignore must exclude '{item}'"

    res_example = _run_git_check_ignore([".env.example"], check=False)
    assert res_example.returncode != 0, ".env.example must remain trackable"


def test_cross_platform_requirements_env_example_and_vision_fallback():
    req_lines = [
        line.strip()
        for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    pyobjc_lines = [line for line in req_lines if line.lower().startswith("pyobjc")]
    assert pyobjc_lines, "Expected pyobjc dependencies in requirements.txt"
    for line in pyobjc_lines:
        assert 'sys_platform == "darwin"' in line, f"pyobjc dependency must be gated to macOS: {line}"

    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ("APP_PORT=8050", "BASE_CURRENCY=GBP", "APP_TIMEZONE=Europe/London", "BACKUP_DIR"):
        assert key in env_example, f".env.example should document {key}"

    # Verify app/vision_parser.py imports cleanly when Quartz/Vision are absent (Linux/Windows simulation)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.modules['Quartz'] = None; sys.modules['Vision'] = None; "
                "import app.vision_parser as vp; assert vp.Quartz is None and vp.Vision is None"
            ),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, f"app/vision_parser.py crashed without pyobjc: {probe.stderr}"


def test_readme_documents_real_entrypoints_scripts_and_commands():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    pkg_json = (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    assert '"build"' in pkg_json and '"test"' in pkg_json

    expected_tokens = [
        "./scripts/install.sh",
        "./scripts/install.sh --dry-run",
        "./scripts/uninstall.sh",
        "./scripts/uninstall.sh --dry-run",
        "--purge-data",
        "com.financehub.app",
        "financehub.service",
        ".env.example",
        "APP_PORT",
        "BASE_CURRENCY",
        "APP_TIMEZONE",
        "BACKUP_DIR",
        "app_timezone",
        "finance_hub_backup_YYYY-MM-DD_HHMMSS.zip",
        "python -m app.restore",
        "./venv/bin/pytest",
        "npm --prefix frontend test",
        "npm --prefix frontend run build",
        "127.0.0.1",
        "FallbackReceiptParser",
    ]
    for token in expected_tokens:
        assert token in readme, f"README.md is missing documented token: {token}"

    for script in ("scripts/install.sh", "scripts/uninstall.sh", "run.py", "app/restore.py", ".env.example"):
        assert (REPO_ROOT / script).exists(), f"Documented file missing: {script}"


def test_real_scripts_dry_run_mode_against_isolated_home(tmp_path):
    fake_home = tmp_path / "dry_home"
    fake_xdg = tmp_path / "dry_xdg"
    fake_home.mkdir()
    fake_xdg.mkdir()
    env = dict(os.environ, HOME=str(fake_home), XDG_CONFIG_HOME=str(fake_xdg))

    res_install = subprocess.run(
        [str(REPO_ROOT / "scripts" / "install.sh"), "--dry-run", "--port", "8061"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_install.returncode == 0, res_install.stderr
    assert "[DRY-RUN]" in res_install.stdout
    assert "8061" in res_install.stdout
    assert not any(fake_home.rglob("*")), "--dry-run must not write anything to HOME"

    res_uninstall = subprocess.run(
        [str(REPO_ROOT / "scripts" / "uninstall.sh"), "--dry-run"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_uninstall.returncode == 0, res_uninstall.stderr
    assert "[KEEP]" in res_uninstall.stdout and "data" in res_uninstall.stdout


@pytest.mark.parametrize("platform_name", ["Darwin", "Linux"])
def test_sandbox_install_idempotency_and_uninstall_data_preservation(tmp_path, platform_name):
    sandbox_proj, service_log, env = _setup_isolated_sandbox(tmp_path, platform_name)

    install_cmd = [str(sandbox_proj / "scripts" / "install.sh"), "--port", "8099"]
    # Run twice to prove idempotent install / upgrade without harming data
    first = subprocess.run(install_cmd, cwd=str(sandbox_proj), env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    second = subprocess.run(install_cmd, cwd=str(sandbox_proj), env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stdout + second.stderr

    # Verify build outputs exist & service file uses generic label + sandbox paths
    assert (sandbox_proj / "venv" / "bin" / "python").exists()
    assert (sandbox_proj / "frontend" / "dist" / "index.html").exists()

    if platform_name == "Darwin":
        plist_path = Path(env["HOME"]) / "Library" / "LaunchAgents" / "com.financehub.app.plist"
        assert plist_path.exists()
        root = ET.fromstring(plist_path.read_text(encoding="utf-8"))
        plist_text = plist_path.read_text(encoding="utf-8")
        assert "com.financehub.app" in plist_text
        assert str(sandbox_proj) in plist_text
        assert "8099" in plist_text
        assert not re.search(r"/Users/[^/]+", str(plist_text.replace(str(sandbox_proj), ""))), "No hardcoded user path in plist"
        assert root.tag == "plist"
        calls = service_log.read_text(encoding="utf-8")
        assert "launchctl bootstrap" in calls
        service_file = plist_path
    else:
        unit_path = Path(env["XDG_CONFIG_HOME"]) / "systemd" / "user" / "financehub.service"
        assert unit_path.exists()
        unit_text = unit_path.read_text(encoding="utf-8")
        assert f"WorkingDirectory={sandbox_proj}" in unit_text
        assert f"ExecStart={sandbox_proj}/venv/bin/python {sandbox_proj}/run.py" in unit_text
        assert "Environment=APP_PORT=8099" in unit_text
        assert not re.search(r"/home/[^/]+", str(unit_text.replace(str(sandbox_proj), ""))), "No hardcoded user path in unit"
        calls = service_log.read_text(encoding="utf-8")
        assert "systemctl --user enable --now financehub.service" in calls
        service_file = unit_path

    # Pre-existing financial data MUST remain byte-for-byte untouched after repeated installs
    assert (sandbox_proj / "data" / "finances.db").read_bytes() == b"SQLite-sentinel-default"
    assert (sandbox_proj / "data" / "profiles" / "shared" / "finances.db").read_bytes() == b"SQLite-sentinel-profile"
    assert (sandbox_proj / "data" / "receipts" / "sample_receipt.jpg").read_bytes() == b"receipt-sentinel"
    assert (sandbox_proj / "data" / "backups" / "backup_sentinel.zip").read_bytes() == b"zip-sentinel"
    assert (sandbox_proj / ".env").read_text(encoding="utf-8") == "APP_PORT=8077\n"

    # Default uninstall (even with --yes, WITHOUT --purge-data) removes service/build deps but preserves ./data & .env
    uninstall_default = subprocess.run(
        [str(sandbox_proj / "scripts" / "uninstall.sh"), "--yes"],
        cwd=str(sandbox_proj),
        env=env,
        capture_output=True,
        text=True,
    )
    assert uninstall_default.returncode == 0, uninstall_default.stdout + uninstall_default.stderr
    assert not service_file.exists(), "Service definition must be removed"
    assert not (sandbox_proj / "venv").exists()
    assert not (sandbox_proj / "frontend" / "node_modules").exists()
    assert not (sandbox_proj / "frontend" / "dist").exists()
    assert (sandbox_proj / "data" / "finances.db").read_bytes() == b"SQLite-sentinel-default"
    assert (sandbox_proj / "data" / "profiles" / "shared" / "finances.db").read_bytes() == b"SQLite-sentinel-profile"
    assert (sandbox_proj / "data" / "receipts" / "sample_receipt.jpg").read_bytes() == b"receipt-sentinel"
    assert (sandbox_proj / "data" / "backups" / "backup_sentinel.zip").read_bytes() == b"zip-sentinel"
    assert (sandbox_proj / ".env").read_text(encoding="utf-8") == "APP_PORT=8077\n"

    # Non-interactive --purge-data without --yes must refuse and preserve ./data
    purge_refused = subprocess.run(
        [str(sandbox_proj / "scripts" / "uninstall.sh"), "--purge-data"],
        cwd=str(sandbox_proj),
        env=env,
        input="wrong\n",
        capture_output=True,
        text=True,
    )
    assert purge_refused.returncode != 0
    assert (sandbox_proj / "data" / "finances.db").exists()

    # Dry-run --purge-data must preview exact contents and still preserve ./data
    purge_dry = subprocess.run(
        [str(sandbox_proj / "scripts" / "uninstall.sh"), "--dry-run", "--purge-data"],
        cwd=str(sandbox_proj),
        env=env,
        capture_output=True,
        text=True,
    )
    assert purge_dry.returncode == 0
    assert "[DRY-RUN]" in purge_dry.stdout
    assert "SQLite DBs: 2" in purge_dry.stdout
    assert "backup ZIPs: 1" in purge_dry.stdout
    assert "finances.db" in purge_dry.stdout
    assert "backup_sentinel.zip" in purge_dry.stdout
    assert (sandbox_proj / "data" / "finances.db").exists()

    # Explicit --purge-data --yes removes ./data while still leaving .env intact
    purge_confirmed = subprocess.run(
        [str(sandbox_proj / "scripts" / "uninstall.sh"), "--purge-data", "--yes"],
        cwd=str(sandbox_proj),
        env=env,
        capture_output=True,
        text=True,
    )
    assert purge_confirmed.returncode == 0, purge_confirmed.stdout + purge_confirmed.stderr
    assert not (sandbox_proj / "data").exists()
    assert (sandbox_proj / ".env").read_text(encoding="utf-8") == "APP_PORT=8077\n"


def test_fresh_database_initialization_stamps_alembic_head_and_upgrades_cleanly(tmp_path):
    """Verifies brand-new DB creation stamps Alembic head so `alembic upgrade head` is safe."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect as sa_inspect, text
    from app.database import configure_sqlite_engine, get_alembic_head_revision, initialize_database_schema

    db_path = tmp_path / "fresh_init.db"
    eng = configure_sqlite_engine(f"sqlite:///{db_path}")
    try:
        initialize_database_schema(eng)
        with eng.connect() as conn:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver == get_alembic_head_revision()
    finally:
        eng.dispose()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    # Legacy DB with pre-existing tables but no alembic_version must NOT be falsely stamped
    legacy_db = tmp_path / "legacy_unversioned.db"
    legacy_eng = configure_sqlite_engine(f"sqlite:///{legacy_db}")
    try:
        with legacy_eng.begin() as conn:
            conn.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);"))
        initialize_database_schema(legacy_eng)
        tables = set(sa_inspect(legacy_eng).get_table_names())
        assert "alembic_version" not in tables
    finally:
        legacy_eng.dispose()


def test_config_app_port_validation_and_install_dry_run_env_awareness(tmp_path):
    from app.config import _parse_app_port

    assert _parse_app_port("8050") == 8050
    assert _parse_app_port("18050") == 18050
    for bad in ("abc", "0", "65536", "-1"):
        with pytest.raises(ValueError, match="APP_PORT"):
            _parse_app_port(bad)

    sandbox_proj, _, env = _setup_isolated_sandbox(tmp_path, "Linux")
    # Remove sentinel DB & .env to simulate a brand-new clone
    shutil.rmtree(sandbox_proj / "data")
    (sandbox_proj / ".env").unlink()

    fresh_dry = subprocess.run(
        [str(sandbox_proj / "scripts" / "install.sh"), "--dry-run"],
        cwd=str(sandbox_proj),
        env=env,
        capture_output=True,
        text=True,
    )
    assert fresh_dry.returncode == 0, fresh_dry.stderr
    assert "Fresh installation detected" in fresh_dry.stdout
    assert "BASE_CURRENCY=GBP" in fresh_dry.stdout
    assert "APP_TIMEZONE=Europe/London" in fresh_dry.stdout

    # When .env specifies custom APP_PORT, BASE_CURRENCY, and APP_TIMEZONE, dry-run reflects them
    (sandbox_proj / ".env").write_text(
        "APP_PORT=8079\nBASE_CURRENCY=USD\nAPP_TIMEZONE=America/New_York\n",
        encoding="utf-8",
    )
    custom_dry = subprocess.run(
        [str(sandbox_proj / "scripts" / "install.sh"), "--dry-run", "--no-service"],
        cwd=str(sandbox_proj),
        env=env,
        capture_output=True,
        text=True,
    )
    assert custom_dry.returncode == 0, custom_dry.stderr
    assert "http://127.0.0.1:8079" in custom_dry.stdout
    assert "BASE_CURRENCY=USD" in custom_dry.stdout
    assert "APP_TIMEZONE=America/New_York" in custom_dry.stdout
