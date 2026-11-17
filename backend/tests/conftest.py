"""Общая настройка тестов: отдельный каталог с конфигами и отдельная SQLite-база.

Переменные окружения выставляются до импорта приложения, потому что
engine БД и настройки создаются при импорте модулей.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DIR = Path(tempfile.mkdtemp(prefix="cfg-"))

common = (BACKEND_DIR / "config.yaml").read_text(encoding="utf-8")
# Тестовая БД во временном каталоге, а не в каталоге проекта.
common = common.replace(
    "sqlite:///./campaign_editor.db", "sqlite:///" + (TEST_DIR / "test.db").as_posix()
)
(TEST_DIR / "config.yaml").write_text(common, encoding="utf-8")
(TEST_DIR / "local_config.yaml").write_text(
    'keitaro:\n  base_url: https://keitaro.test\n  api_key: "test-key"\n',
    encoding="utf-8",
)
os.environ["CAMPAIGN_EDITOR_CONFIG_DIR"] = str(TEST_DIR)


@pytest.fixture()
def config_dir() -> Path:
    return TEST_DIR
