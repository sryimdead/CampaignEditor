from typing import Literal

import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Допустимые коды стран ISO 3166-1 alpha-2 (US, DE, BR ...).
VALID_COUNTRY_CODES: frozenset[str] = frozenset(c.alpha_2 for c in pycountry.countries)


class CampaignUpdate(BaseModel):
    """Частичное обновление: в Keitaro уйдут только явно переданные поля."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    alias: str | None = Field(default=None, max_length=255)
    group_id: int | None = None
    traffic_source_id: int | None = None
    state: Literal["active", "disabled"] | None = None
    cost_type: str | None = None
    cost_value: float | None = None
    notes: str | None = None


class CampaignCreatorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    geos: list[str] = Field(min_length=1, max_length=len(VALID_COUNTRY_CODES))
    offer_ids: list[int] = Field(min_length=1, max_length=50, description="ID офферов в Keitaro")
    # Закреплённые веса (offer_id -> процент). Остальные офферы делят остаток поровну.
    weights: dict[int, int] = Field(default_factory=dict)

    @field_validator("offer_ids")
    @classmethod
    def _check_offer_ids(cls, values: list[int]) -> list[int]:
        result: list[int] = []
        for v in values:
            if v <= 0:
                raise ValueError("ID оффера должен быть больше 0")
            if v not in result:  # дубликаты убираем, порядок сохраняем
                result.append(v)
        return result

    @field_validator("weights")
    @classmethod
    def _check_weights(cls, values: dict[int, int]) -> dict[int, int]:
        for oid, share in values.items():
            if not 1 <= share <= 100:
                raise ValueError(f"вес оффера #{oid} должен быть от 1 до 100")
        return values

    @model_validator(mode="after")
    def _weights_belong_to_offers(self):
        extra = set(self.weights) - set(self.offer_ids)
        if extra:
            raise ValueError(f"веса заданы для офферов, которых нет в списке: {sorted(extra)}")
        return self

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("название не должно быть пустым")
        return v

    @field_validator("geos")
    @classmethod
    def _check_geos(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for raw in values:
            code = str(raw).strip().upper()
            if code not in VALID_COUNTRY_CODES:
                raise ValueError(f"«{raw}» не код страны ISO 3166-1 alpha-2")
            if code not in result:  # дубликаты убираем, порядок сохраняем
                result.append(code)
        return result


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str
    action: str
    keitaro_campaign_id: int | None
    payload: dict


class OfferAddIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: int = Field(gt=0, description="ID оффера в Keitaro")


class OfferWeightIn(BaseModel):
    """share - закрепить вес в процентах; null - снять закрепление (вес снова автоматический)."""

    model_config = ConfigDict(extra="forbid")

    share: int | None = Field(default=None, ge=1, le=100)


class OfferPreviewIn(BaseModel):
    """Предпросмотр весов без обращения к Keitaro."""

    model_config = ConfigDict(extra="forbid")

    offer_ids: list[int] = Field(default_factory=list, max_length=50)
    pins: dict[int, int] = Field(default_factory=dict)
