"""Загрузка и валидация конфигурации.

Конфиг собирается из двух файлов в одном каталоге:
  config.yaml        - общие настройки, хранятся в git;
  local_config.yaml  - секреты и адрес трекера, в git не попадают.
Значения из local_config.yaml переопределяют config.yaml.
Каталог можно сменить переменной окружения CAMPAIGN_EDITOR_CONFIG_DIR.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = Path(os.environ.get("CAMPAIGN_EDITOR_CONFIG_DIR", BASE_DIR))
COMMON_FILE = "config.yaml"
LOCAL_FILE = "local_config.yaml"


class ConfigError(RuntimeError):
    """Ошибка чтения или валидации конфигурации. Сообщение пригодно для вывода пользователю."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppSettings(_Strict):
    database_url: str = "sqlite:///./campaign_editor.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class CountryFilter(_Strict):
    # Поля фильтра в Keitaro: name, mode (accept/reject), payload (список кодов через запятую).
    name: str = Field(default="country", min_length=1)
    mode: Literal["accept", "reject"] = "accept"


class GeoRedirectStream(_Strict):
    """Поток для выбранных стран: редирект на внешний URL (google.com)."""

    # В YAML ключ называется "schema", в Python - stream_schema (schema - служебное имя в pydantic)
    stream_schema: str = Field(default="redirect", alias="schema", min_length=1)
    url: AnyHttpUrl
    position: int = Field(default=1, ge=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OfferStream(_Strict):
    """Поток для всех остальных посетителей: без фильтров, ведёт на оффер."""

    stream_schema: str = Field(default="landings", alias="schema", min_length=1)
    position: int = Field(default=2, ge=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StreamSettings(_Strict):
    type: str = Field(default="regular", min_length=1)
    country_filter: CountryFilter = Field(default_factory=CountryFilter)
    geo_redirect: GeoRedirectStream
    offer: OfferStream = Field(default_factory=OfferStream)

    @model_validator(mode="after")
    def _positions_ordered(self):
        if self.geo_redirect.position >= self.offer.position:
            raise ValueError("geo_redirect.position должен быть меньше offer.position")
        return self


class CampaignDefaults(_Strict):
    """Значения, которые подставляются в каждую создаваемую кампанию."""

    domain: str = Field(min_length=1)
    group_name: str = Field(min_length=1)
    traffic_source_name: str = Field(min_length=1)
    # Значение поля type при создании кампании (способ ротации потоков в Keitaro).
    # Точные допустимые значения сверьте с вашим Keitaro: по умолчанию position.
    campaign_type: str = Field(default="position", min_length=1)


class KeitaroSettings(_Strict):
    base_url: AnyHttpUrl
    api_key: SecretStr
    api_key_header: str = Field(default="Api-Key", min_length=1)
    timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    campaign_defaults: CampaignDefaults
    stream: StreamSettings = Field(default_factory=StreamSettings)

    @field_validator("api_key")
    @classmethod
    def _api_key_not_blank(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("не должен быть пустым")
        return v

    @field_validator("base_url", mode="after")
    @classmethod
    def _no_admin_api_suffix(cls, v: AnyHttpUrl) -> AnyHttpUrl:
        if "/admin_api" in str(v):
            raise ValueError("укажите адрес трекера без /admin_api/v1")
        return v


class Settings(_Strict):
    app: AppSettings = Field(default_factory=AppSettings)
    keitaro: KeitaroSettings


def _read_yaml(path: Path, *, required: bool) -> dict[str, Any]:
    if path.is_dir():
        # Docker создаёт каталог вместо файла, если bind-монтирование выполнено до создания файла
        raise ConfigError(f"{path} - это каталог, а не файл. Создайте файл local_config.yaml до запуска.")
    if not path.exists():
        if required:
            raise ConfigError(f"Файл {path} не найден")
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Ошибка разбора YAML в {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} должен содержать словарь верхнего уровня")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _format_errors(exc: ValidationError, sources: str) -> str:
    lines = [f"Ошибки конфигурации ({sources}):"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def load_settings(config_dir: Path | None = None) -> Settings:
    directory = Path(config_dir) if config_dir is not None else CONFIG_DIR
    common = _read_yaml(directory / COMMON_FILE, required=True)
    local_path = directory / LOCAL_FILE
    if not local_path.exists():
        raise ConfigError(
            f"Не найден {local_path}. Скопируйте local_config.example.yaml в {LOCAL_FILE} "
            "и укажите адрес и API-ключ Keitaro."
        )
    local = _read_yaml(local_path, required=True)
    merged = _deep_merge(common, local)
    try:
        return Settings.model_validate(merged)
    except ValidationError as exc:
        raise ConfigError(_format_errors(exc, f"{COMMON_FILE}, {LOCAL_FILE}")) from exc


@lru_cache
def get_settings() -> Settings:
    return load_settings()
