import shutil
from pathlib import Path

import pytest

from app.config import BASE_DIR, ConfigError, load_settings

COMMON = BASE_DIR / "config.yaml"


def _make_dir(tmp_path: Path, local: str | None) -> Path:
    shutil.copy(COMMON, tmp_path / "config.yaml")
    if local is not None:
        (tmp_path / "local_config.yaml").write_text(local, encoding="utf-8")
    return tmp_path


def test_loads_valid_config(tmp_path):
    d = _make_dir(
        tmp_path,
        'keitaro:\n  base_url: https://k.example.com\n  api_key: "abc"\n',
    )
    s = load_settings(d)
    assert str(s.keitaro.base_url).startswith("https://k.example.com")
    assert s.keitaro.api_key.get_secret_value() == "abc"
    # Значения из общего config.yaml подтянулись
    assert s.keitaro.api_key_header == "Api-Key"
    assert s.keitaro.stream.offer.stream_schema == "landings"
    assert s.keitaro.stream.geo_redirect.stream_schema == "redirect"
    assert str(s.keitaro.stream.geo_redirect.url).rstrip("/") == "https://www.google.com"
    assert s.keitaro.stream.country_filter.name == "country"
    assert s.keitaro.stream.country_filter.mode == "accept"


def test_redirect_must_come_before_offer(tmp_path):
    d = _make_dir(tmp_path, 'keitaro:\n  base_url: https://k.example.com\n  api_key: "abc"\n')
    text = (d / "config.yaml").read_text(encoding="utf-8").replace("position: 1\n", "position: 3\n")
    (d / "config.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="position"):
        load_settings(d)


def test_local_overrides_common(tmp_path):
    d = _make_dir(
        tmp_path,
        'keitaro:\n  base_url: https://k.example.com\n  api_key: "abc"\n'
        "  timeout_seconds: 30\n",
    )
    assert load_settings(d).keitaro.timeout_seconds == 30


def test_missing_local_file_is_clear_error(tmp_path):
    d = _make_dir(tmp_path, None)
    with pytest.raises(ConfigError, match="local_config.example.yaml"):
        load_settings(d)


def test_empty_api_key_rejected(tmp_path):
    d = _make_dir(tmp_path, 'keitaro:\n  base_url: https://k.example.com\n  api_key: "   "\n')
    with pytest.raises(ConfigError, match="keitaro.api_key"):
        load_settings(d)


def test_admin_api_suffix_rejected(tmp_path):
    d = _make_dir(
        tmp_path,
        'keitaro:\n  base_url: https://k.example.com/admin_api/v1\n  api_key: "abc"\n',
    )
    with pytest.raises(ConfigError, match="без /admin_api"):
        load_settings(d)


def test_unknown_key_rejected(tmp_path):
    d = _make_dir(
        tmp_path,
        'keitaro:\n  base_url: https://k.example.com\n  api_key: "abc"\n  typo_field: 1\n',
    )
    with pytest.raises(ConfigError, match="typo_field"):
        load_settings(d)


def test_filter_operator_and_action_are_not_accepted(tmp_path):
    # Keitaro не принимает operator/action у фильтра, поэтому конфиг их тоже не допускает
    d = _make_dir(tmp_path, 'keitaro:\n  base_url: https://k.example.com\n  api_key: "abc"\n')
    text = (d / "config.yaml").read_text(encoding="utf-8").replace(
        "name: country\n", "name: country\n      action: accept\n", 1
    )
    (d / "config.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="action"):
        load_settings(d)


def test_invalid_yaml_reported(tmp_path):
    d = _make_dir(tmp_path, "keitaro: [unclosed\n")
    with pytest.raises(ConfigError, match="YAML"):
        load_settings(d)
