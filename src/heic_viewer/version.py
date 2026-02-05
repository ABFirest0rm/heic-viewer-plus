import requests

ORG_NAME = "AbeyAjit"
SETTINGS_APP_NAME = "HeicViewer"
APP_NAME = "HEIC Viewer+"
APP_VERSION = "1.0.0"

def version_string():
    return f"{APP_NAME} v{APP_VERSION}"

GITHUB_VERSION_URL = (
    "https://raw.githubusercontent.com/ABFirest0rm/heic-viewer-plus/main/version.txt"
)

def check_for_updates(current_version):
    try:
        r = requests.get(GITHUB_VERSION_URL, timeout=3)
        if r.status_code != 200:
            return None

        latest = r.text.strip()
        if latest != current_version:
            return latest
        return None
    except Exception:
        return None