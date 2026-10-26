"""Mocked SDK tests: zero network calls or live credentials."""
import json
from types import SimpleNamespace

import pytest

from config import Config, diagnostics
from providers.factory import make_provider
from providers.vertex import ImagePayload, ProviderUnavailable


def test_developer_uses_key_not_adc_and_disables_sdk_retries(monkeypatch):
    from google import genai
    observed = {}
    response = SimpleNamespace(text='{"ok":true}', usage_metadata=SimpleNamespace(total_token_count=17))
    class Client:
        def __init__(self, **kwargs): observed.update(kwargs); self.models = self
        def generate_content(self, **kwargs): observed["request"] = kwargs; return response
        def close(self): observed["closed"] = True
    monkeypatch.setattr(genai, "Client", Client)
    config = Config.from_env({"LLM_PROVIDER":"gemini_developer", "GEMINI_API_KEY":"private-test-value", "GEMINI_MODEL_ID":"test"})
    provider = make_provider(config)
    result = provider.generate(system_instruction="JSON", prompt="Inspect", images=[
        ImagePayload(b"actual-image-bytes", "image/png", "desired_reference", "sketch")])
    assert json.loads(result)["ok"]
    assert observed["vertexai"] is False and observed["api_key"] == config.gemini_api_key
    assert "project" not in observed and "location" not in observed
    assert observed["http_options"].retry_options.attempts == 1
    assert observed["request"]["contents"][-1].inline_data.data == b"actual-image-bytes"
    assert observed["request"]["config"].response_mime_type == "application/json"
    assert provider.last_usage["total_token_count"] == 17 and observed["closed"]
    assert config.gemini_api_key not in repr(config)
    assert config.gemini_api_key not in json.dumps(diagnostics(config))


def test_secret_in_sdk_exception_is_not_exposed(monkeypatch):
    from google import genai
    secret = "private-test-value"
    def fail(**kwargs): raise RuntimeError("URL?key=" + secret)
    monkeypatch.setattr(genai, "Client", fail)
    provider = make_provider(Config.from_env({"LLM_PROVIDER":"gemini_developer", "GEMINI_API_KEY":secret, "GEMINI_MODEL_ID":"test"}))
    with pytest.raises(ProviderUnavailable) as caught:
        provider.generate(system_instruction="JSON", prompt="test")
    import traceback
    assert secret not in "".join(traceback.format_exception(caught.value))


def test_dotenv_is_root_only_no_interpolation_and_env_wins(monkeypatch, tmp_path):
    import config as module
    (tmp_path / ".env").write_text("LLM_PROVIDER=gemini_developer\nGEMINI_API_KEY=local-test-key\nGEMINI_MODEL_ID=${DO_NOT_EXPAND}\n")
    monkeypatch.setattr(module, "__file__", str(tmp_path / "config.py"))
    for name in ("LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    config = Config.from_env()
    assert config.llm_provider == "vertex" and config.gemini_api_key == "local-test-key"
    assert config.gemini_model_id == "${DO_NOT_EXPAND}"
    assert Config.from_env({}).gemini_api_key is None
