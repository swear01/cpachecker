#!/usr/bin/env python3
"""Create a Zenodo DRAFT deposition, upload the artifact, and set metadata.

Does NOT publish: it stops at a draft for the user to review and publish manually.
The API token is read from the environment (never hard-coded or printed).

Usage:
    ZENODO_BASE=https://sandbox.zenodo.org ZENODO_TOKEN=xxx \
        python3 artifact/zenodo_upload.py vguide-artifact.zip
    # for the real DOI, set ZENODO_BASE=https://zenodo.org with a production token
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ZENODO_BASE", "https://sandbox.zenodo.org").rstrip("/")
TOKEN = os.environ.get("ZENODO_TOKEN")
ZIP = sys.argv[1] if len(sys.argv) > 1 else "vguide-artifact.zip"
META_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".zenodo.json")

if not TOKEN:
    sys.exit("ZENODO_TOKEN not set in environment")


def api(method, url, data=None, raw=None, content_type=None):
    if not url.startswith("http"):
        url = BASE + url
    headers = {"Authorization": "Bearer " + TOKEN}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        body = raw
        headers["Content-Type"] = content_type or "application/octet-stream"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        return e.code, (json.loads(txt) if txt else {})


def main():
    print("Zenodo base:", BASE)
    # 1. create empty draft
    st, dep = api("POST", "/api/deposit/depositions", data={})
    if st >= 300:
        sys.exit("create draft failed: %s %s" % (st, dep))
    dep_id = dep["id"]
    bucket = dep["links"]["bucket"]
    print("draft created, id =", dep_id)

    # 2. upload the archive into the draft's bucket (streamed; handles large files)
    fn = os.path.basename(ZIP)
    size = os.path.getsize(ZIP)
    with open(ZIP, "rb") as f:
        req = urllib.request.Request(
            bucket + "/" + fn, data=f, method="PUT",
            headers={"Authorization": "Bearer " + TOKEN,
                     "Content-Type": "application/octet-stream",
                     "Content-Length": str(size)})
        try:
            with urllib.request.urlopen(req) as r:
                up = json.loads(r.read().decode() or "{}")
                st = r.status
        except urllib.error.HTTPError as e:
            sys.exit("upload failed: %s %s" % (e.code, e.read().decode()))
    print("uploaded %s (%d bytes), checksum=%s" % (fn, size, up.get("checksum", "?")))

    # 3. metadata (adapt .zenodo.json to the deposition schema)
    z = json.load(open(META_FILE))
    allowed = ["title", "upload_type", "publication_date", "description", "creators",
               "keywords", "access_right", "license", "version", "language", "notes",
               "method", "related_identifiers", "references", "contributors",
               "communities", "grants", "subjects", "locations", "dates"]
    meta = {k: z[k] for k in allowed if z.get(k)}
    meta.setdefault("upload_type", "software")
    meta.setdefault("access_right", "open")
    st, r = api("PUT", "/api/deposit/depositions/%s" % dep_id, data={"metadata": meta})
    if st >= 300:
        print("metadata rejected (%s): %s" % (st, r.get("errors", r)))
        meta.pop("license", None)  # license id mismatch is the usual culprit; set it in the UI
        st, r = api("PUT", "/api/deposit/depositions/%s" % dep_id, data={"metadata": meta})
        print("metadata retry without license:", st)
    else:
        print("metadata set:", st)

    # 4. publish only if explicitly requested (ZENODO_PUBLISH=1); otherwise leave a draft.
    if os.environ.get("ZENODO_PUBLISH") == "1":
        st, pub = api("POST", "/api/deposit/depositions/%s/actions/publish" % dep_id)
        if st >= 300:
            sys.exit("PUBLISH failed: %s %s" % (st, pub.get("errors", pub)))
        links = pub.get("links", {})
        print("\nPUBLISHED.")
        print("  DOI:", pub.get("doi") or pub.get("metadata", {}).get("doi"))
        print("  Record:", links.get("record_html") or links.get("html"))
    else:
        st, dep = api("GET", "/api/deposit/depositions/%s" % dep_id)
        html = dep.get("links", {}).get("html") or (BASE + "/deposit/%s" % dep_id)
        print("\nDRAFT ready (NOT published). Review and publish here:")
        print("  ", html)
        print("Deposition id:", dep_id, "  state:", dep.get("state"))


if __name__ == "__main__":
    main()
