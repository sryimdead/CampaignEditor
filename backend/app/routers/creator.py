"""Создатель кампании.

Одним запросом создаётся кампания с доменом, группой и источником из конфига
(FORTESTS по умолчанию) и по одному потоку на каждое выбранное гео,
все потоки ведут на один оффер.
"""

import re
import secrets
import string

import pycountry
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..dependencies import get_keitaro
from ..keitaro import KeitaroClient, KeitaroError
from ..models import CampaignChange, OfferPin
from ..schemas import CampaignCreatorIn, OfferPreviewIn
from ..services.offer_weights import WeightError, compute_shares

router = APIRouter(prefix="/api", tags=["creator"])


def _upstream_status(exc: KeitaroError) -> int:
    return exc.status_code if 400 <= exc.status_code < 500 else 502


def _find_id(items: list[dict], name: str, what: str) -> int:
    """ID элемента Keitaro по имени. Сначала точное совпадение, потом без учёта регистра."""
    for item in items:
        if item.get("name") == name:
            return item["id"]
    for item in items:
        if str(item.get("name", "")).casefold() == name.casefold():
            return item["id"]
    raise HTTPException(
        status_code=422,
        detail=f"{what} «{name}» не найден в Keitaro. Проверьте config.yaml или создайте его в Keitaro.",
    )


_ALIAS_CHARS = string.ascii_lowercase + string.digits


def _generate_alias(length: int = 8) -> str:
    """Случайный alias кампании: Keitaro требует его при создании."""
    return "".join(secrets.choice(_ALIAS_CHARS) for _ in range(length))


def _check_offers(kt: KeitaroClient, offer_ids: list[int]) -> None:
    """Проверяем, что все офферы существуют в Keitaro, до создания кампании."""
    try:
        known = {o.get("id") for o in kt.list_offers()}
    except KeitaroError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=exc.detail) from exc
    missing = [oid for oid in offer_ids if oid not in known]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Офферы не найдены в Keitaro: "
            + ", ".join(f"#{oid}" for oid in missing)
            + ". Выберите офферы из списка.",
        )


def _resolve_defaults(kt: KeitaroClient) -> dict:
    d = get_settings().keitaro.campaign_defaults
    try:
        return {
            "domain_id": _find_id(kt.list_domains(), d.domain, "Домен"),
            "group_id": _find_id(kt.list_groups(), d.group_name, "Группа"),
            "traffic_source_id": _find_id(kt.list_traffic_sources(), d.traffic_source_name, "Источник трафика"),
            "type": d.campaign_type,
        }
    except KeitaroError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=exc.detail) from exc


def _build_streams(
    campaign_id: int, campaign_name: str, offers: list[dict], geos: list[str]
) -> list[tuple[str, dict]]:
    """offers - список {offer_id, share} с уже рассчитанными весами."""
    """Два потока: выбранные страны -> google.com (первый), остальные -> оффер (второй)."""
    s = get_settings().keitaro.stream
    f = s.country_filter
    redirect = s.geo_redirect
    geo_stream = {
        "campaign_id": campaign_id,
        "name": f"{campaign_name} · {', '.join(geos)} → google",
        "type": s.type,
        "schema": redirect.stream_schema,
        "position": redirect.position,
        "state": "active",
        "filters": [{"name": f.name, "mode": f.mode, "payload": ",".join(geos)}],
        # Адрес редиректа: действие потока (action_type) и его значение (action_payload)
        "action_type": "http",
        "action_payload": str(redirect.url),
    }
    offer_stream = {
        "campaign_id": campaign_id,
        # Имя не содержит ID офферов: их список меняется, название должно оставаться понятным
        "name": f"{campaign_name} · остальные → офферы",
        "type": s.type,
        "schema": s.offer.stream_schema,
        "position": s.offer.position,
        "state": "active",
        # Keitaro требует action_type и для потока на оффер; без действия он пустой ("http" без payload)
        "action_type": "http",
        "action_payload": "",
        "offers": offers,
    }
    return [("гео на google.com", geo_stream), ("остальные на оффер", offer_stream)]


@router.post("/campaign-creator", status_code=201)
def create_campaign_with_offer(
    body: CampaignCreatorIn,
    kt: KeitaroClient = Depends(get_keitaro),
    db: Session = Depends(get_db),
):
    # Все ID разрешаем до создания чего-либо, чтобы не оставлять кампанию без потоков из-за опечатки в конфиге.
    _check_offers(kt, body.offer_ids)
    try:
        shares = compute_shares(body.offer_ids, body.weights)
    except WeightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ids = _resolve_defaults(kt)
    campaign_payload = {"name": body.name, "alias": _generate_alias(), "state": "active", **ids}
    offers_payload = [{"offer_id": oid, "share": shares[oid]} for oid in body.offer_ids]

    try:
        campaign = kt.create_campaign(campaign_payload)
    except KeitaroError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=exc.detail) from exc

    campaign_id = campaign["id"]
    streams: list[dict] = []
    for label, payload in _build_streams(campaign_id, body.name, offers_payload, body.geos):
        try:
            streams.append(kt.create_stream(payload))
        except KeitaroError as exc:
            # Не оставляем кампанию активной с неполным набором потоков.
            try:
                kt.update_campaign(campaign_id, {"state": "disabled"})
                note = f"Кампания #{campaign_id} выключена."
            except KeitaroError:
                note = f"Кампания #{campaign_id} создана и не выключена, выключите её вручную."
            created = ", ".join(s.get("name", str(s.get("id"))) for s in streams) or "нет"
            raise HTTPException(
                status_code=_upstream_status(exc),
                detail=(
                    f"Поток «{label}» не создан. {note} "
                    f"Созданные потоки: {created}. Ошибка Keitaro: {exc.detail}"
                ),
            ) from exc

    for oid, share in body.weights.items():
        db.add(OfferPin(keitaro_campaign_id=campaign_id, offer_id=oid, share=share))
    db.add(
        CampaignChange(
            action="create_with_offer",
            keitaro_campaign_id=campaign_id,
            payload={"campaign": campaign_payload, "stream_ids": [s.get("id") for s in streams]},
        )
    )
    db.commit()
    return {"campaign": campaign, "streams": streams}


@router.get("/meta/countries")
def list_countries():
    """Страны для выбора геокодов: код ISO alpha-2 и название."""
    return sorted(
        ({"code": c.alpha_2, "name": c.name} for c in pycountry.countries),
        key=lambda c: c["name"],
    )


def _clean_offer_name(offer_id: int | None, name: str) -> str:
    """Убирает ID из начала названия: «12284 Flexacil» -> «Flexacil».

    Интерфейс сам показывает ID, поэтому повтор в названии не нужен.
    """
    if offer_id is None:
        return name.strip()
    cleaned = re.sub(rf"^\s*#?{offer_id}(?!\d)[\s\-·:.|)]*", "", name).strip()
    return cleaned or name.strip()


@router.post("/offer-weights/preview")
def preview_weights(body: OfferPreviewIn):
    """Веса офферов по правилам приложения, без записи в Keitaro. Используется формами."""
    pins = {oid: share for oid, share in body.pins.items() if oid in body.offer_ids}
    try:
        shares = compute_shares(body.offer_ids, pins)
    except WeightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "total": sum(shares.values()),
        "offers": [
            {"offer_id": oid, "share": shares[oid], "pinned": oid in pins} for oid in body.offer_ids
        ],
    }


@router.get("/meta/offers")
def list_offers(kt: KeitaroClient = Depends(get_keitaro)):
    """Офферы из Keitaro для выбора в форме создателя."""
    try:
        offers = kt.list_offers()
    except KeitaroError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=exc.detail) from exc
    return [{"id": o.get("id"), "name": _clean_offer_name(o.get("id"), o.get("name", ""))} for o in offers]


@router.get("/meta/creator-defaults")
def creator_defaults():
    """Значения, которые автоматически проставляются в каждую кампанию (показываются в форме)."""
    d = get_settings().keitaro.campaign_defaults
    return {"domain": d.domain, "group_name": d.group_name, "traffic_source_name": d.traffic_source_name}
