from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_streamlit_api_key_routes_are_opt_in_only():
    source = APP.read_text(encoding="utf-8")

    assert "def _streamlit_api_key_routes_enabled" in source
    assert "STREAMLIT_ENABLE_API_KEY_AI" in source
    assert "if api_key_routes_enabled:" in source


def test_streamlit_oauth_proxy_routes_precede_openai_api_key_fallback():
    source = APP.read_text(encoding="utf-8")
    body = source[source.index("def call_claude(") : source.index("def _is_ai_unavailable_text")]

    direct = body.index("_call_claude_direct(")
    proxy = body.index("_call_claude_proxy(")
    openai = body.index("_call_openai_api_key(")

    assert direct < proxy < openai


if __name__ == "__main__":
    test_streamlit_api_key_routes_are_opt_in_only()
    test_streamlit_oauth_proxy_routes_precede_openai_api_key_fallback()
