"""Publishes frontend/dist on Firebase Hosting through its REST API, with the gcloud session.

Using the REST API avoids a separate Firebase CLI login: the gcloud account that deploys the
backend also publishes the frontend. Hosting settings (headers, rewrites, cleanUrls) come from
`frontend/firebase.json`, the same file the Firebase CLI would read.

Usage: `deploy_hosting.py <site> <project>` (run `npm run build` in frontend/ first).
"""

import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
API = "https://firebasehosting.googleapis.com/v1beta1"
TIMEOUT_S = 120


class Hosting:
    def __init__(self, project: str) -> None:
        self._project = project
        self._token = _access_token()

    def call(
        self, method: str, url: str, body: object = None, *, raw: bytes | None = None
    ) -> dict[str, object]:
        payload = raw if raw is not None else None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=payload, method=method)  # noqa: S310
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("X-Goog-User-Project", self._project)
        if payload is not None:
            content_type = "application/octet-stream" if raw is not None else "application/json"
            request.add_header("Content-Type", content_type)
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
            text = response.read().decode()
        parsed: object = json.loads(text) if text else {}
        if not isinstance(parsed, dict):
            message = f"Unexpected response from {url}"
            raise TypeError(message)
        return parsed


def _access_token() -> str:
    gcloud = shutil.which("gcloud") or str(Path.home() / "google-cloud-sdk/bin/gcloud")
    result = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [gcloud, "auth", "print-access-token"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def hosting_config() -> dict[str, object]:
    """`firebase.json` hosting settings in the REST API's shape (`source` becomes `glob`)."""
    loaded: object = json.loads((FRONTEND / "firebase.json").read_text())
    if not isinstance(loaded, dict) or not isinstance(loaded.get("hosting"), dict):
        message = "frontend/firebase.json has no hosting section"
        raise TypeError(message)
    hosting: dict[str, object] = loaded["hosting"]
    rewrites = _entries(hosting, "rewrites")
    headers = _entries(hosting, "headers")
    return {
        "cleanUrls": bool(hosting.get("cleanUrls", False)),
        "rewrites": [{"glob": rule["source"], "path": rule["destination"]} for rule in rewrites],
        "headers": [
            {"glob": rule["source"], "headers": {h["key"]: h["value"] for h in _pairs(rule)}}
            for rule in headers
        ],
    }


def _entries(hosting: dict[str, object], key: str) -> list[dict[str, str | list[object]]]:
    value = hosting.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        message = f"firebase.json: hosting.{key} must be a list of objects"
        raise TypeError(message)
    return value


def _pairs(rule: dict[str, str | list[object]]) -> list[dict[str, str]]:
    pairs = rule.get("headers", [])
    result: list[dict[str, str]] = []
    for pair in pairs if isinstance(pairs, list) else [None]:
        if not isinstance(pair, dict):
            message = "firebase.json: each headers rule needs a list of {key, value}"
            raise TypeError(message)
        result.append({"key": str(pair["key"]), "value": str(pair["value"])})
    return result


def gzipped_files(dist: Path) -> dict[str, bytes]:
    """Every built file, gzipped deterministically (Hosting identifies files by this hash)."""
    return {
        "/" + path.relative_to(dist).as_posix(): gzip.compress(path.read_bytes(), mtime=0)
        for path in sorted(dist.rglob("*"))
        if path.is_file()
    }


def deploy(site: str, project: str) -> str:
    dist = FRONTEND / "dist"
    if not (dist / "index.html").is_file():
        message = "frontend/dist is missing: build the frontend first"
        raise FileNotFoundError(message)
    files = gzipped_files(dist)
    hashes = {name: hashlib.sha256(blob).hexdigest() for name, blob in files.items()}
    hosting = Hosting(project)

    version = hosting.call("POST", f"{API}/sites/{site}/versions", {"config": hosting_config()})
    name = str(version["name"])
    populated = hosting.call("POST", f"{API}/{name}:populateFiles", {"files": hashes})
    required = populated.get("uploadRequiredHashes", [])
    upload_url = str(populated.get("uploadUrl", ""))
    for file_name, blob in files.items():
        if isinstance(required, list) and hashes[file_name] in required:
            hosting.call("POST", f"{upload_url}/{hashes[file_name]}", raw=blob)
    hosting.call("PATCH", f"{API}/{name}?update_mask=status", {"status": "FINALIZED"})
    hosting.call("POST", f"{API}/sites/{site}/releases?versionName={name}", {})
    uploaded = len(required) if isinstance(required, list) else 0
    return f"{len(files)} files ({uploaded} new) published on https://{site}.web.app\n"


if __name__ == "__main__":
    if len(sys.argv) != 3:  # noqa: PLR2004 - program name plus two arguments
        sys.stderr.write("usage: deploy_hosting.py <site> <project>\n")
        sys.exit(2)
    sys.stdout.write(deploy(sys.argv[1], sys.argv[2]))
