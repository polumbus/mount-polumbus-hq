from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_streamlit_api_key_routes_are_opt_in_only():
    source = APP.read_text(encoding="utf-8")

    assert "def _streamlit_api_key_routes_enabled" in source
    assert "def _streamlit_ai_profile_status" in source
    assert "STREAMLIT_ENABLE_API_KEY_AI" in source
    assert "if api_key_routes_enabled:" in source
    assert "profile_violation" in source


def test_streamlit_oauth_proxy_routes_precede_openai_api_key_fallback():
    source = APP.read_text(encoding="utf-8")
    body = source[source.index("def call_claude(") : source.index("def _is_ai_unavailable_text")]

    direct = body.index("_call_claude_direct(")
    proxy = body.index("_call_claude_proxy(")
    openai = body.index("_call_openai_api_key(")

    assert direct < proxy < openai


def test_streamlit_openai_api_key_failure_is_gated_from_default_profile():
    source = APP.read_text(encoding="utf-8")
    body = source[source.index("def call_claude(") : source.index("def _is_ai_unavailable_text")]
    openai_block = body[body.index("# 4. Optional OpenAI API-key fallback") :]

    assert "if api_key_routes_enabled:" in openai_block
    assert 'return "AI unavailable — OAuth, proxy, and local Codex OAuth routes all failed."' in body
    assert "No OPENAI_API_KEY configured" not in body.split("# 4. Optional OpenAI API-key fallback", 1)[0]


def test_creator_evolution_provider_normalizer_preserves_chatgpt_choice():
    source = APP.read_text(encoding="utf-8")
    body = source[source.index("def _ce_normalize_ai_provider") : source.index("def _ce_selected_ai_provider")]

    assert '{"chatgpt", "chat gpt", "openai", "gpt"}' in body
    assert 'return "ChatGPT"' in body
    assert '{"grok", "xai", "x.ai"}' in body
    assert 'return "Grok"' in body


def test_streamlit_secret_lookup_has_local_secrets_fallback():
    source = APP.read_text(encoding="utf-8")
    body = source[source.index("def _secret_or_env") : source.index("def _running_on_streamlit_cloud")]

    assert "def _local_streamlit_secret" in source
    assert 'APP_DIR / ".streamlit" / "secrets.toml"' in source
    assert "value = os.environ.get(name, \"\")" in body
    assert "value = _local_streamlit_secret(name)" in body


def test_creator_evolution_grok_uses_proxy_when_direct_key_missing():
    source = APP.read_text(encoding="utf-8")
    body = source[source.index("def _call_creator_evolution_ai_for_provider") : source.index("def _call_creator_evolution_ai(")]

    assert "def _call_grok_proxy" in source
    assert "grok missing direct key; trying proxy route" in body
    assert "_call_grok_proxy(prompt, system_prompt, max_tokens" in body
    assert '"ready via HQ proxy"' in source


def test_voice_tuner_is_in_mobile_owner_nav():
    source = APP.read_text(encoding="utf-8")
    mobile_nav = source[source.index("# ── Mobile hamburger nav") : source.index("page = st.session_state.current_page")]

    assert "page=Voice+Tuner" in mobile_nav
    assert "Voice Tuner" in mobile_nav


def test_creator_evolution_whats_hot_uses_studio_discovery_cache():
    source = APP.read_text(encoding="utf-8")
    runner = source[source.index("def _run_creator_evolution_hot_signals") : source.index("def _ce_pulse_error_decision")]
    dialog = source[source.index("def _ce_inspiration_dialog") : source.index("@st.dialog(\"Creator Studio\"")]

    assert "def _whats_hot_studio_cache_key" in source
    assert "_load_inspo_from_gist(_studio_cache_key)" in runner
    assert "_run_inspiration_claude(_studio_cache_key)" in runner
    assert "len(_all_tweets)" not in runner
    assert '"studio_cache_key": _studio_cache_key' in dialog
    assert "_run_creator_evolution_hot_signals(_studio_cache_key, _lane, _fmt)" in dialog


def test_voice_tuner_feedback_regenerates_and_cannot_be_replaced_by_fallback():
    source = APP.read_text(encoding="utf-8")
    generate_body = source[source.index("def _ce_testing_generate(") : source.index("def _ce_testing_generate_pair")]
    page_body = source[source.index("def page_voice_tuner") : source.index("def page_testing")]

    assert "def _ce_testing_feedback_lines" in source
    assert "applied_feedback = _ce_testing_feedback_lines(lab_state, lane) if testing_copy else []" in generate_body
    assert "len(passing_ids) < 3 and not applied_feedback" in generate_body
    assert '"applied_feedback": applied_feedback[-20:]' in generate_body
    assert "next_gen_key = _ce_voice_tuner_generation_key(item, provider, state, selected_lane, selected_fmt)" in page_body
    assert "Regenerating A/B test with your feedback" in page_body
    assert "Feedback saved and regenerated." in page_body


if __name__ == "__main__":
    test_streamlit_api_key_routes_are_opt_in_only()
    test_streamlit_oauth_proxy_routes_precede_openai_api_key_fallback()
    test_streamlit_openai_api_key_failure_is_gated_from_default_profile()
    test_creator_evolution_provider_normalizer_preserves_chatgpt_choice()
    test_streamlit_secret_lookup_has_local_secrets_fallback()
    test_creator_evolution_grok_uses_proxy_when_direct_key_missing()
    test_voice_tuner_is_in_mobile_owner_nav()
    test_creator_evolution_whats_hot_uses_studio_discovery_cache()
    test_voice_tuner_feedback_regenerates_and_cannot_be_replaced_by_fallback()
