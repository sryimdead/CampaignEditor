from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import get_keitaro
from ..keitaro import KeitaroClient, KeitaroError
from ..models import CampaignChange
from ..schemas import CampaignUpdate, ChangeOut

router = APIRouter(prefix="/api", tags=["campaigns"])


def _upstream(exc: KeitaroError) -> HTTPException:
    # Ошибки 4xx от Keitaro пробрасываем как есть, 5xx и сеть -> 502.
    status = exc.status_code if 400 <= exc.status_code < 500 else 502
    return HTTPException(status_code=status, detail=exc.detail)


def _log(db: Session, action: str, campaign_id: int | None, payload: dict) -> None:
    db.add(CampaignChange(action=action, keitaro_campaign_id=campaign_id, payload=payload))
    db.commit()


@router.get("/campaigns")
def list_campaigns(kt: KeitaroClient = Depends(get_keitaro)):
    try:
        return kt.list_campaigns()
    except KeitaroError as exc:
        raise _upstream(exc) from exc


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, kt: KeitaroClient = Depends(get_keitaro)):
    try:
        return kt.get_campaign(campaign_id)
    except KeitaroError as exc:
        raise _upstream(exc) from exc


@router.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: int,
    body: CampaignUpdate,
    kt: KeitaroClient = Depends(get_keitaro),
    db: Session = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="Нет полей для обновления")
    try:
        updated = kt.update_campaign(campaign_id, data)
    except KeitaroError as exc:
        raise _upstream(exc) from exc
    _log(db, "update", campaign_id, data)
    return updated


@router.get("/meta/groups")
def list_groups(kt: KeitaroClient = Depends(get_keitaro)):
    try:
        return kt.list_groups()
    except KeitaroError as exc:
        raise _upstream(exc) from exc


@router.get("/meta/traffic-sources")
def list_traffic_sources(kt: KeitaroClient = Depends(get_keitaro)):
    try:
        return kt.list_traffic_sources()
    except KeitaroError as exc:
        raise _upstream(exc) from exc


@router.get("/changes", response_model=list[ChangeOut])
def list_changes(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(CampaignChange).order_by(CampaignChange.id.desc()).limit(limit)).all()
    return [
        ChangeOut(
            id=r.id,
            created_at=r.created_at.isoformat(),
            action=r.action,
            keitaro_campaign_id=r.keitaro_campaign_id,
            payload=r.payload,
        )
        for r in rows
    ]
