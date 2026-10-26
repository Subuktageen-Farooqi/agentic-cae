import json

import pytest

from config import Config, diagnostics


def test_diagnostics_never_print_config_values_credentials_or_claim_execution(tmp_path):
    secret = "should-never-appear-in-output"
    adc = tmp_path / "private-credentials.json"
    adc.write_text(json.dumps({"private_key": secret}), encoding="utf-8")
    config = Config.from_env({"GOOGLE_CLOUD_PROJECT": secret, "GOOGLE_CLOUD_LOCATION": secret,
                              "GEMINI_MODEL_ID": secret, "GOOGLE_APPLICATION_CREDENTIALS": str(adc)})
    report = diagnostics(config)
    output = json.dumps(report)
    assert secret not in output and str(adc) not in output
    assert report["vertex"]["adc_file_present"] is True
    assert report["vertex"]["authentication"] == "unverified"
    assert report["mechanical"]["license"] == "unverified"
    assert report["freecad"]["execution"] == "unverified"


def test_no_openai_key_or_default_cloud_project_required():
    config = Config.from_env({})
    assert config.google_project is None and config.gemini_model_id is None
    assert config.worker_timeout_seconds == 300


@pytest.mark.parametrize("values", [{"CAE_WORKER_TIMEOUT_SECONDS": "0"}, {"CAE_CONTAINER_RUNTIME": "cmd.exe"}])
def test_invalid_worker_configuration_rejected(values):
    with pytest.raises(ValueError):
        Config.from_env(values)
