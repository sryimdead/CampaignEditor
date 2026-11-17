"""Офферы кампании: список, добавление, удаление и веса.

В Keitaro офферы живут внутри потока (схема keitaro.stream.offer.stream_schema).
Веса считаются здесь: незакреплённые делят остаток до 100 поровну,
закреплённый вес не меняется при добавлении и удалении других офферов.
Закрепления хранятся локально в таблице offer_pins.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..dependencies import get_keitaro
from ..keitaro import KeitaroClient, KeitaroError
from ..models import CampaignChange, OfferPin
from ..routers.creator import _clean_offer_name
from ..schemas import OfferAddIn, OfferWeightIn
from ..services.offer_weights import WeightError, compute_shares

router = APIRouter(prefix="/api/campaigns/{campaign_id}/offers", tags=["campaign-offers"])

# Поля потока, которые Keitaro требует при обновлении (берём их из текущего потока).
_STREAM_FIELDS = ("name", "type", "schema", "position", "state", "action_type", "action_payload")


def _status(exc: KeitaroError) -> int:
    return exc.status_code if 400 <= exc.status_code < 500 else 502


def _offer_stream(kt: KeitaroClient, campaign_id: int) -> dict:
    schema = get_settings().keitaro.stream.offer.stream_schema
    try:
        streams = kt.list_streams(campaign_id)
    except KeitaroError as exc:
        raise HTTPException(status_code=_status(exc), detail=exc.detail) from exc
    for s in streams:
        if s.get("schema") == schema:
            return s
    raise HTTPException(status_code=404, detail="В кампании нет потока с офферами")


def _names(kt: KeitaroClient) -> dict[int, str]:
    try:
        return {o["id"]: _clean_offer_name(o["id"], o.get("name", "")) for o in kt.list_offers()}
    except KeitaroError as exc:
        raise HTTPException(status_code=_status(exc), detail=exc.detail) from exc


def _pins(db: Session, campaign_id: int) -> dict[int, int]:
    rows = db.scalars(select(OfferPin).where(OfferPin.keitaro_campaign_id == campaign_id)).all()
    return {r.offer_id: r.share for r in rows}


def _offer_ids(stream: dict) -> list[int]:
    return [o["offer_id"] for o in stream.get("offers", [])]


def _recalc(offer_ids: list[int], pins: dict[int, int]) -> dict[int, int]:
    try:
        return compute_shares(offer_ids, pins)
    except WeightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _view(offer_ids: list[int], shares: dict[int, int], pins: dict[int, int], names: dict[int, str]) -> list[dict]:
    return [
        {
            "offer_id": oid,
            "name": names.get(oid, ""),
            "share": shares[oid],
            "pinned": oid in pins,
        }
        for oid in offer_ids
    ]


def _save(kt: KeitaroClient, stream: dict, shares: dict[int, int]) -> None:
    body = {k: stream[k] for k in _STREAM_FIELDS if k in stream}
    body["offers"] = [{"offer_id": oid, "share": share} for oid, share in shares.items()]
    try:
        kt.update_stream(stream["id"], body)
    except KeitaroError as exc:
        raise HTTPException(status_code=_status(exc), detail=exc.detail) from exc


def _response(stream: dict, shares: dict[int, int], pins: dict[int, int], names: dict[int, str]) -> dict:
    return {
        "stream_id": stream["id"],
        "total": sum(shares.values()),
        "offers": _view(list(shares), shares, pins, names),
    }


@router.get("")
def list_offers(campaign_id: int, kt: KeitaroClient = Depends(get_keitaro), db: Session = Depends(get_db)):
    stream = _offer_stream(kt, campaign_id)
    ids = _offer_ids(stream)
    pins = _pins(db, campaign_id)
    shares = _recalc(ids, pins)
    return _response(stream, shares, pins, _names(kt))


@router.post("")
def add_offer(
    campaign_id: int,
    body: OfferAddIn,
    kt: KeitaroClient = Depends(get_keitaro),
    db: Session = Depends(get_db),
):
    names = _names(kt)
    if body.offer_id not in names:
        raise HTTPException(status_code=422, detail=f"Оффер #{body.offer_id} не найден в Keitaro")
    stream = _offer_stream(kt, campaign_id)
    ids = _offer_ids(stream)
    if body.offer_id in ids:
        raise HTTPException(status_code=422, detail=f"Оффер #{body.offer_id} уже в кампании")
    pins = _pins(db, campaign_id)
    shares = _recalc(ids + [body.offer_id], pins)  # новый оффер не закреплён: получит автоматический вес
    _save(kt, stream, shares)
    db.add(CampaignChange(action="offer_add", keitaro_campaign_id=campaign_id, payload={"offer_id": body.offer_id}))
    db.commit()
    return _response(stream, shares, pins, names)


@router.delete("/{offer_id}")
def remove_offer(
    campaign_id: int,
    offer_id: int,
    kt: KeitaroClient = Depends(get_keitaro),
    db: Session = Depends(get_db),
):
    names = _names(kt)
    stream = _offer_stream(kt, campaign_id)
    ids = _offer_ids(stream)
    if offer_id not in ids:
        raise HTTPException(status_code=404, detail=f"Оффер #{offer_id} не в кампании")
    remaining = [oid for oid in ids if oid != offer_id]
    if not remaining:
        raise HTTPException(status_code=422, detail="Нельзя удалить последний оффер кампании")
    pins = {k: v for k, v in _pins(db, campaign_id).items() if k != offer_id}
    shares = _recalc(remaining, pins)
    _save(kt, stream, shares)
    db.execute(
        delete(OfferPin).where(
            OfferPin.keitaro_campaign_id == campaign_id, OfferPin.offer_id == offer_id
        )
    )
    db.add(CampaignChange(action="offer_remove", keitaro_campaign_id=campaign_id, payload={"offer_id": offer_id}))
    db.commit()
    return _response(stream, shares, pins, names)


@router.put("/{offer_id}/weight")
def set_weight(
    campaign_id: int,
    offer_id: int,
    body: OfferWeightIn,
    kt: KeitaroClient = Depends(get_keitaro),
    db: Session = Depends(get_db),
):
    """Закрепить вес оффера (share) или снять закрепление (share = null)."""
    names = _names(kt)
    stream = _offer_stream(kt, campaign_id)
    ids = _offer_ids(stream)
    if offer_id not in ids:
        raise HTTPException(status_code=404, detail=f"Оффер #{offer_id} не в кампании")

    pins = dict(_pins(db, campaign_id))
    if body.share is None:
        pins.pop(offer_id, None)
    else:
        pins[offer_id] = body.share
    shares = _recalc(ids, pins)  # при ошибке ничего не сохраняем
    _save(kt, stream, shares)

    existing = db.scalar(
        select(OfferPin).where(OfferPin.keitaro_campaign_id == campaign_id, OfferPin.offer_id == offer_id)
    )
    if body.share is None:
        if existing:
            db.delete(existing)
    elif existing:
        existing.share = body.share
    else:
        db.add(OfferPin(keitaro_campaign_id=campaign_id, offer_id=offer_id, share=body.share))
    db.add(
        CampaignChange(
            action="offer_weight",
            keitaro_campaign_id=campaign_id,
            payload={"offer_id": offer_id, "share": body.share},
        )
    )
    db.commit()
    return _response(stream, shares, pins, names)
