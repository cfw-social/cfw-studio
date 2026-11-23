"""Small helpers shared by the b-hyperframes scripts. Standard library only."""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

OK, FAIL, USAGE, MISSING = 0, 1, 2, 3

BLOCK_DIR = Path(__file__).resolve().parent.parent
PINS_FILE = BLOCK_DIR / "pins.json"

# The only environment variables a child process receives, besides the ones
# this block sets itself. Nothing else (keys, tokens, proxies) is passed on.
PASS_THROUGH = (
    "PATH", "LANG", "LC_ALL", "SYSTEMROOT", "COMSPEC", "PATHEXT", "WINDIR",
)
TRUST_FILE = ".hf-trust.json"


class Stop(Exception):
    """Raised to end a script with a plain message and an exit code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def real(path):
    return Path(os.path.realpath(path))


def is_inside(path, root):
    p, r = real(path), real(root)
    return p == r or r in p.parents


def has_symlink_below(root, path):
    """True when any part of path below root is a symbolic link."""
    root, path = Path(os.path.abspath(root)), Path(os.path.abspath(path))
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            return True
    return False


def work_folder(arg):
    work = Path(arg) if arg else Path.cwd()
    if not work.is_dir():
        raise Stop(USAGE, f"work folder not found: {work}")
    return real(work)


def inside_work(arg, work, what):
    """Resolve a path given on the command line; it must stay inside the work folder."""
    p = Path(arg)
    p = p if p.is_absolute() else Path.cwd() / p
    if not is_inside(p, work):
        raise Stop(USAGE, f"{what} must be inside the work folder ({work}): {arg}")
    if has_symlink_below(work, os.path.normpath(p)):
        raise Stop(USAGE, f"{what} passes through a symbolic link, which is refused: {arg}")
    return Path(os.path.normpath(p))


def ensure_dir(path, work, what):
    """Create a folder inside the work folder; refuse links before and after creating it."""
    path = inside_work(path, work, what)
    path.mkdir(parents=True, exist_ok=True)
    return inside_work(path, work, what)


def refuse_linked_children(folder, work, what):
    """A symbolic link directly inside a folder this block writes to or runs from is refused."""
    for child in Path(folder).iterdir():
        if child.is_symlink():
            raise Stop(USAGE, f"{what} holds a symbolic link, which is refused: {child}")


def atomic_write(path, data, mode=0o644):
    """Write through an exclusive temporary file, then replace. Never writes through a link."""
    path = Path(path)
    if path.is_symlink():
        raise Stop(USAGE, f"refusing to replace a symbolic link: {path}")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".part-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def entry_hashes(runtime):
    """SHA-256 of the package's own entry files: its package.json and the scripts directly in dist/."""
    pkg = Path(runtime) / "node_modules" / "hyperframes"
    files = [pkg / "package.json"] + sorted((pkg / "dist").glob("*.js"))
    return {str(f.relative_to(runtime)).replace(os.sep, "/"): sha256_file(f) for f in files if f.is_file()}


def load_pins(path=None):
    try:
        return json.loads(Path(path or PINS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Stop(MISSING, f"cannot read pins file: {exc}")


def safe_env(cache_dir, extra=None):
    """Environment for a child process: a short allow-list plus a cache inside the work folder."""
    env = {k: os.environ[k] for k in PASS_THROUGH if k in os.environ}
    cache = str(cache_dir)
    tmp = str(Path(cache_dir) / "tmp")
    env.update({"HOME": cache, "USERPROFILE": cache, "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp})
    if extra:
        env.update(extra)
    return env


def run_main(main):
    try:
        code = main()
    except Stop as stop:
        print(f"{Path(sys.argv[0]).name}: {stop.message}", file=sys.stderr)
        code = stop.code
    except Exception:  # last resort: one fixed line, no traceback
        print(f"{Path(sys.argv[0]).name}: unexpected error (details withheld; rerun after checking the inputs)", file=sys.stderr)
        code = FAIL
    sys.exit(code or 0)
