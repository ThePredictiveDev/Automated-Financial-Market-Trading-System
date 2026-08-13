"""CORS allow-list for the TradeFlow REST API (order / Risk Gate)."""

from web_server import PRODUCTION_FRONTEND_ORIGIN, _cors_origins, _load_cors_origins


def test_production_vercel_origin_is_always_allowed():
    assert PRODUCTION_FRONTEND_ORIGIN == "https://tradeflow-demo-omega.vercel.app"
    assert PRODUCTION_FRONTEND_ORIGIN in _cors_origins
    assert "http://localhost:5173" in _cors_origins
    assert "http://127.0.0.1:5173" in _cors_origins


def test_cors_origins_env_merges_instead_of_replacing_defaults():
    origins = _load_cors_origins("https://preview.example.com")
    assert "http://localhost:5173" in origins
    assert PRODUCTION_FRONTEND_ORIGIN in origins
    assert "https://preview.example.com" in origins


def test_cors_origins_strips_trailing_slashes():
    origins = _load_cors_origins("https://extra.example.com/")
    assert "https://extra.example.com" in origins
    assert "https://extra.example.com/" not in origins


def test_empty_cors_origins_env_keeps_localhost_and_production():
    origins = _load_cors_origins("")
    assert origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        PRODUCTION_FRONTEND_ORIGIN,
    ]
