from __future__ import annotations

from services.cookie_store import validate_cookies_txt


def test_validate_netscape_cookie_text() -> None:
    valid, reason, line_count = validate_cookies_txt(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\ttest-value\n"
    )
    assert valid is True
    assert reason == "ok"
    assert line_count == 1


def test_reject_invalid_cookie_text() -> None:
    valid, reason, line_count = validate_cookies_txt("hello world")
    assert valid is False
    assert "Netscape" in reason or "cookie" in reason.lower()
    assert line_count == 0
