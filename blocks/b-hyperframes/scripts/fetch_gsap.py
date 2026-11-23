#!/usr/bin/env python3
"""Fetch the pinned GSAP build from the public npm registry and verify it.

    python3 fetch_gsap.py --outdir work/vendor

Writes OUTDIR/gsap.min.js and OUTDIR/gsap.min.js.json (version and checksums).
GSAP is third-party code under GreenSock's own licence. It is never stored in this
repository. Exit codes: 0 done, 1 verification or download failed, 2 bad usage,
3 pins file missing.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hfcommon import FAIL, OK, USAGE, Stop, atomic_write, ensure_dir, load_pins, run_main, work_folder  # noqa: E402

REGISTRY = "https://registry.npmjs.org"
MAX_TARBALL = 8 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
TIMEOUT = 60


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def registry_ok(url):
    parts = urllib.parse.urlsplit(url)
    if url.rstrip("/") == REGISTRY:
        return True
    return parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")


def get(url, limit):
    """GET without following redirects; the body is capped."""
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "cfw-studio-b-hyperframes"})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            body = resp.read(limit + 1)
    except (urllib.error.URLError, OSError) as exc:
        raise Stop(FAIL, f"download failed for {url}: {exc}")
    if len(body) > limit:
        raise Stop(FAIL, f"download from {url} is larger than {limit} bytes; refused")
    return body


def same_origin(url, registry):
    a, b = urllib.parse.urlsplit(url), urllib.parse.urlsplit(registry)
    return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)


def integrity_of(data):
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def verify_and_extract(tarball, meta, pin):
    """Check the tarball against the registry value and the pin, return the library bytes."""
    published = meta.get("dist", {}).get("integrity", "")
    if not published.startswith("sha512-"):
        raise Stop(FAIL, "the registry did not publish a sha512 integrity value for this version")
    if pin["tarball_integrity"] != published:
        raise Stop(FAIL, "the registry integrity value differs from the pinned one; refused")
    actual = integrity_of(tarball)
    if actual != published:
        raise Stop(FAIL, f"tarball integrity mismatch: registry says {published}, download is {actual}")
    sha1 = meta.get("dist", {}).get("shasum")
    if sha1 and hashlib.sha1(tarball).hexdigest() != sha1:
        raise Stop(FAIL, "tarball sha1 differs from the registry shasum")
    member = pin["file"]
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
            info = tar.getmember(member)
            if not info.isreg() or info.size > MAX_FILE:
                raise Stop(FAIL, f"{member} in the tarball is not a regular file of a sane size")
            data = tar.extractfile(info).read()
    except (tarfile.TarError, KeyError, OSError) as exc:
        raise Stop(FAIL, f"cannot read {member} from the tarball: {exc}")
    want = pin["file_sha256"]
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise Stop(FAIL, f"library file sha256 {got} does not match the pinned {want}")
    return data, actual, got


def require_pins(pin):
    """Both checksums must be present in any pins file; a missing key is a usage error."""
    ok = (isinstance(pin.get("version"), str) and isinstance(pin.get("file"), str)
          and str(pin.get("tarball_integrity", "")).startswith("sha512-")
          and len(str(pin.get("file_sha256", ""))) == 64)
    if not ok:
        raise Stop(USAGE, "the pins file must give version, file, tarball_integrity (sha512-...) and file_sha256 (64 hex)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--outdir", required=True, help="folder inside the work folder")
    ap.add_argument("--work", help="work folder (default: current folder)")
    ap.add_argument("--registry", default=REGISTRY, help="test use only: a http://127.0.0.1 or localhost URL")
    ap.add_argument("--pins", help="test use only: another pins file")
    ap.add_argument("--force", action="store_true", help="fetch again even if a verified file is present")
    args = ap.parse_args()

    if not registry_ok(args.registry):
        raise Stop(USAGE, "--registry must be https://registry.npmjs.org or a http://127.0.0.1 / localhost URL")
    work = work_folder(args.work)
    pins = load_pins(args.pins).get("gsap")
    if not isinstance(pins, dict):
        raise Stop(USAGE, "the pins file has no gsap entry")
    require_pins(pins)
    outdir = ensure_dir(args.outdir, work, "--outdir")
    version = pins["version"]
    target, sidecar = outdir / "gsap.min.js", outdir / "gsap.min.js.json"
    if target.is_symlink() or sidecar.is_symlink():
        raise Stop(USAGE, "gsap.min.js or its record is a symbolic link; refused")

    if not args.force and target.is_file() and sidecar.is_file():
        have = hashlib.sha256(target.read_bytes()).hexdigest()
        if have == pins["file_sha256"]:
            print(f"gsap {version} already present and matches the pin", file=sys.stderr)
            print(target)
            return OK

    registry = args.registry.rstrip("/")
    meta_url = f"{registry}/gsap/{urllib.parse.quote(version)}"
    try:
        meta = json.loads(get(meta_url, 1024 * 1024))
    except ValueError as exc:
        raise Stop(FAIL, f"registry answer is not JSON: {exc}")
    if meta.get("version") != version:
        raise Stop(FAIL, f"registry returned version {meta.get('version')}, expected {version}")
    tar_url = meta.get("dist", {}).get("tarball", "")
    if not same_origin(tar_url, registry):
        raise Stop(FAIL, f"tarball address is not on the registry host: {tar_url}")
    data, tar_integrity, file_sha = verify_and_extract(get(tar_url, MAX_TARBALL), meta, pins)

    atomic_write(target, data)
    record = {
        "package": "gsap",
        "version": version,
        "source": tar_url,
        "tarball_integrity": tar_integrity,
        "file": pins["file"],
        "file_sha256": file_sha,
        "licence": "GreenSock standard licence, https://gsap.com/standard-license. Third-party code, not part of this repository.",
    }
    atomic_write(sidecar, (json.dumps(record, indent=2) + "\n").encode())
    print(f"gsap {version} verified (registry integrity and pin agree)", file=sys.stderr)
    print(target)
    return OK


if __name__ == "__main__":
    run_main(main)
