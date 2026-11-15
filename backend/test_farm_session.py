from fastapi import Request, Response

import main


def test_exit_farm_session_expires_only_the_browser_cookie(monkeypatch):
    monkeypatch.setattr(main, "require_allowed_origin", lambda request: None)
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/api/farms/session/exit", "query_string": b"", "server": ("test", 80), "scheme": "http", "client": ("test", 1), "root_path": ""})
    response = Response()

    result = main.exit_farm_session(request, response)

    assert result == {"session_ended": True}
    cookie = response.headers["set-cookie"]
    assert main.COOKIE_NAME in cookie
    assert "Max-Age=0" in cookie
    assert "Path=/api" in cookie

