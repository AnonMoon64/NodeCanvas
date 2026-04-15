#!/usr/bin/env python3
import sys, os, json
from PyQt6.QtCore import QSettings
import urllib.request, urllib.error

# Ensure repo root on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def main():
    settings = QSettings("NodeCanvas", "AI")
    api_key = settings.value("api_key", "") or ""
    if not api_key:
        print("No API key found in settings (NodeCanvas/AI api_key)")
        return 2

    url = "https://api.mistral.ai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            ct = resp.getheader("Content-Type", "") or ""
            if "application/json" in ct:
                obj = json.loads(body.decode("utf-8"))
                print(json.dumps(obj, indent=2))
                return 0
            else:
                print(body.decode("utf-8", errors="replace"))
                return 0
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        print(f"HTTP Error {getattr(e,'code',None)}: {getattr(e,'reason',None)} - {body}")
        return 2
    except urllib.error.URLError as e:
        print(f"URL Error: {e}")
        return 2

if __name__ == "__main__":
    sys.exit(main())
