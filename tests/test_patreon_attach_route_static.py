"""Static check: the held-media attach route must be reachable over POST.

do_POST rejects any path missing from its allowlist set with a 404 before dispatch,
so a handler branch alone is not enough (this shipped broken once on 2026-11-17).
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
ROUTE = "/api/patreon-attach-held-media"


def _post_allowlist(src: str) -> str:
    m = re.search(r'if self\.path not in \{(.*?)\}:\s*\n\s*self\.send_error\(404\)', src, re.S)
    assert m, "POST allowlist block not found in app.py"
    return m.group(1)


def test_attach_route_in_post_allowlist():
    src = APP.read_text(encoding="utf-8")
    assert f'"{ROUTE}"' in _post_allowlist(src)


def test_attach_route_dispatches_to_handler():
    src = APP.read_text(encoding="utf-8")
    assert re.search(r'if self\.path == "' + re.escape(ROUTE) + r'":\s*\n\s*self\.send_json\(attach_held_patreon_media\(', src)
