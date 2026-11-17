import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dependencies import get_keitaro
from app.keitaro import KeitaroClient
from app.main import create_app
from app.models import CampaignChange, OfferPin

# conftest.py уже выставил CAMPAIGN_EDITOR_CONFIG_DIR и тестовую БД.


class FakeKeitaro:
    """Запоминает запросы и отвечает как Keitaro Admin API."""

    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []
        self.campaigns = {1: {"id": 1, "name": "First", "state": "active"}}
        self.streams: list[dict] = []
        # Домен берём из конфига, чтобы тесты не зависели от захардкоженного значения
        self.domains = [{"id": 5, "name": get_settings().keitaro.campaign_defaults.domain}]
        self.groups = [{"id": 7, "name": "FORTESTS"}, {"id": 8, "name": "Other"}]
        self.traffic_sources = [{"id": 9, "name": "fortests"}]  # регистр не важен
        self.offers = [{"id": 42, "name": "42 Nutra offer"}, {"id": 43, "name": "Dating offer"}]
        self.fail_streams = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, body))
        assert request.headers["Api-Key"] == "test-key"

        if request.method == "GET":
            lists = {
                "/admin_api/v1/campaigns": list(self.campaigns.values()),
                "/admin_api/v1/domains": self.domains,
                "/admin_api/v1/groups": self.groups,
                "/admin_api/v1/traffic_sources": self.traffic_sources,
                "/admin_api/v1/offers": self.offers,
            }
            if path in lists:
                return httpx.Response(200, json=lists[path])
        if request.method == "POST" and path == "/admin_api/v1/campaigns":
            new_id = max(self.campaigns) + 1
            self.campaigns[new_id] = {"id": new_id, **body}
            return httpx.Response(201, json=self.campaigns[new_id])
        if request.method == "PUT" and path.startswith("/admin_api/v1/campaigns/"):
            cid = int(path.rsplit("/", 1)[1])
            if cid not in self.campaigns:
                return httpx.Response(404, json={"error": "not found"})
            self.campaigns[cid].update(body)
            return httpx.Response(200, json=self.campaigns[cid])
        if request.method == "GET" and path.startswith("/admin_api/v1/campaigns/") and path.endswith("/streams"):
            cid = int(path.split("/")[4])
            return httpx.Response(200, json=[st for st in self.streams if st["campaign_id"] == cid])
        if request.method == "PUT" and path.startswith("/admin_api/v1/streams/"):
            sid = int(path.rsplit("/", 1)[1])
            for st in self.streams:
                if st["id"] == sid:
                    st.update(body)
                    return httpx.Response(200, json=st)
            return httpx.Response(404, json={"error": "no stream"})
        if request.method == "POST" and path == "/admin_api/v1/streams":
            if self.fail_streams:
                return httpx.Response(422, json={"error": "bad stream"})
            stream = {"id": len(self.streams) + 1, **body}
            self.streams.append(stream)
            return httpx.Response(201, json=stream)
        return httpx.Response(404, text="unexpected")


@pytest.fixture(autouse=True)
def _clean_local_db():
    """Закрепления и журнал живут в общей тестовой БД; ID кампаний в каждом тесте начинаются заново."""
    from app.db import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for model in (OfferPin, CampaignChange):
            db.query(model).delete()
        db.commit()
    yield


@pytest.fixture()
def fake():
    return FakeKeitaro()


@pytest.fixture()
def client(fake):
    app = create_app()

    def override():
        kt = KeitaroClient("https://keitaro.test", "test-key", transport=httpx.MockTransport(fake.handler))
        try:
            yield kt
        finally:
            kt.close()

    app.dependency_overrides[get_keitaro] = override
    with TestClient(app) as c:
        yield c


def _creator(**overrides):
    body = {"name": "  Promo ", "geos": ["US"], "offer_ids": [42]}
    if "offer_id" in overrides:  # удобство тестов: один оффер
        overrides["offer_ids"] = [overrides.pop("offer_id")]
    body.update(overrides)
    return body


# --- Базовое CRUD -----------------------------------------------------------


def test_list_campaigns(client):
    assert client.get("/api/campaigns").json()[0]["name"] == "First"


def test_update_sends_only_provided_fields(client, fake):
    r = client.patch("/api/campaigns/1", json={"state": "disabled"})
    assert r.status_code == 200
    assert fake.calls[-1] == ("PUT", "/admin_api/v1/campaigns/1", {"state": "disabled"})


def test_unknown_field_is_rejected(client):
    assert client.patch("/api/campaigns/1", json={"name": "x", "bogus": 1}).status_code == 422


# --- Создатель: автозаполнение ----------------------------------------------


def test_creator_fills_domain_group_and_source(client, fake):
    r = client.post("/api/campaign-creator", json=_creator())
    assert r.status_code == 201, r.text
    campaign = fake.campaigns[2]
    assert campaign["name"] == "Promo"
    assert campaign["domain_id"] == 5
    assert campaign["group_id"] == 7
    assert campaign["traffic_source_id"] == 9  # найден без учёта регистра
    assert campaign["type"] == get_settings().keitaro.campaign_defaults.campaign_type
    # Keitaro отвечает 422 "Alias is required" без alias
    assert re.fullmatch(r"[a-z0-9]{8}", campaign["alias"])


def test_creator_creates_geo_redirect_and_offer_streams(client, fake):
    r = client.post("/api/campaign-creator", json=_creator(geos=["us", "DE", "BR"]))
    assert r.status_code == 201, r.text
    assert len(fake.streams) == 2
    geo, rest = fake.streams

    # Поток 1: выбранные страны -> google.com
    assert geo["campaign_id"] == 2
    assert geo["position"] == 1
    assert geo["schema"] == "redirect"
    assert geo["action_type"] == "http"
    assert geo["action_payload"].rstrip("/") == "https://www.google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": "US,DE,BR"}]
    assert "offers" not in geo

    # Поток 2: без фильтров, весь остальной трафик -> оффер
    assert rest["campaign_id"] == 2
    assert rest["position"] == 2
    assert rest["schema"] == "landings"
    assert "filters" not in rest
    assert rest["action_type"] == "http"
    # Название общее: по кампании, без ID офферов
    assert rest["name"] == "Promo · остальные → офферы"
    assert "42" not in rest["name"]
    assert geo["name"] == "Promo · US, DE, BR → google"
    assert rest["offers"] == [{"offer_id": 42, "share": 100}]

    assert len(r.json()["streams"]) == 2


def test_creator_deduplicates_geos_keeping_order(client, fake):
    client.post("/api/campaign-creator", json=_creator(geos=["de", "US", "DE"]))
    assert fake.streams[0]["filters"][0]["payload"] == "DE,US"


@pytest.mark.parametrize("geos", [["USA"], ["XX"], ["U S"], ["12"], []])
def test_creator_rejects_invalid_geos(client, geos):
    assert client.post("/api/campaign-creator", json=_creator(geos=geos)).status_code == 422


@pytest.mark.parametrize("offer_id", [0, -1])
def test_creator_rejects_non_positive_offer(client, offer_id):
    assert client.post("/api/campaign-creator", json=_creator(offer_id=offer_id)).status_code == 422


def test_creator_rejects_blank_name(client):
    assert client.post("/api/campaign-creator", json=_creator(name="   ")).status_code == 422


def test_creator_missing_group_creates_nothing(client, fake):
    fake.groups = [{"id": 8, "name": "Other"}]
    r = client.post("/api/campaign-creator", json=_creator())
    assert r.status_code == 422
    assert "FORTESTS" in r.json()["detail"]
    assert 2 not in fake.campaigns  # кампания не создана
    assert not any(c[0] == "POST" for c in fake.calls if c[1] == "/admin_api/v1/campaigns")


def test_creator_disables_campaign_when_stream_fails(client, fake):
    fake.fail_streams = True
    r = client.post("/api/campaign-creator", json=_creator(geos=["DE"]))
    assert r.status_code == 422
    assert "выключена" in r.json()["detail"]
    assert fake.campaigns[2]["state"] == "disabled"


# --- Справочники для формы ---------------------------------------------------


def test_countries_list_is_iso_codes(client):
    countries = client.get("/api/meta/countries").json()
    codes = {c["code"] for c in countries}
    assert {"US", "DE", "BR"} <= codes
    assert len(codes) == 249
    assert all(len(c["code"]) == 2 for c in countries)


def test_creator_defaults_shown_to_form(client):
    data = client.get("/api/meta/creator-defaults").json()
    assert data == {
        "domain": get_settings().keitaro.campaign_defaults.domain,
        "group_name": "FORTESTS",
        "traffic_source_name": "FORTESTS",
    }


# --- Офферы ----------------------------------------------------------------


def test_campaign_streams_use_campaign_path(client, fake):
    # Регрессия: GET /streams?campaign_id=... возвращает 404 в Keitaro
    cid = _make_campaign_with_offers(client, fake)
    client.get(f"/api/campaigns/{cid}/offers")
    assert ("GET", f"/admin_api/v1/campaigns/{cid}/streams", None) in fake.calls


def test_groups_requested_with_campaigns_type(client):
    # Keitaro отвечает 400 "Param 'type' is required" без этого параметра
    seen = {}

    def handler(request):
        seen["query"] = request.url.params.get("type")
        return httpx.Response(200, json=[{"id": 7, "name": "FORTESTS"}])

    kt = KeitaroClient("https://keitaro.test", "test-key", transport=httpx.MockTransport(handler))
    assert kt.list_groups()[0]["id"] == 7
    assert seen["query"] == "campaigns"
    kt.close()


def test_offers_list_comes_from_keitaro(client):
    data = client.get("/api/meta/offers").json()
    # ID в начале названия убран, интерфейс показывает его отдельно
    assert data == [{"id": 42, "name": "Nutra offer"}, {"id": 43, "name": "Dating offer"}]


@pytest.mark.parametrize(
    "offer_id,raw,expected",
    [
        (12284, "12284 Flexacil", "Flexacil"),
        (12284, "#12284 - Flexacil", "Flexacil"),
        (12284, "12284: Flexacil", "Flexacil"),
        (1, "12 Other", "12 Other"),  # другой ID, не трогаем
        (12, "12", "12"),  # название состоит только из ID - оставляем как есть
        (5, "Flexacil 5", "Flexacil 5"),  # ID не в начале - не трогаем
    ],
)
def test_clean_offer_name(offer_id, raw, expected):
    from app.routers.creator import _clean_offer_name

    assert _clean_offer_name(offer_id, raw) == expected


def test_creator_rejects_offer_not_in_keitaro(client, fake):
    r = client.post("/api/campaign-creator", json=_creator(offer_id=999))
    assert r.status_code == 422
    assert "#999" in r.json()["detail"]
    assert 2 not in fake.campaigns  # ничего не создано
    assert not any(c[1] == "/admin_api/v1/campaigns" and c[0] == "POST" for c in fake.calls)


# --- Офферы кампании -------------------------------------------------------


def _make_campaign_with_offers(client, fake, offer_ids=(42,)):
    """Создаёт кампанию через создатель: поток на Google и поток с офферами."""
    r = client.post("/api/campaign-creator", json=_creator(geos=["US"], offer_id=offer_ids[0]))
    assert r.status_code == 201, r.text
    return r.json()["campaign"]["id"]


def test_campaign_offers_listed(client, fake):
    cid = _make_campaign_with_offers(client, fake)
    data = client.get(f"/api/campaigns/{cid}/offers").json()
    assert data["offers"] == [{"offer_id": 42, "name": "Nutra offer", "share": 100, "pinned": False}]


def test_add_offer_updates_offer_stream(client, fake):
    cid = _make_campaign_with_offers(client, fake)
    r = client.post(f"/api/campaigns/{cid}/offers", json={"offer_id": 43})
    assert r.status_code == 200, r.text
    assert [o["offer_id"] for o in r.json()["offers"]] == [42, 43]
    offer_stream = next(s for s in fake.streams if s["schema"] == "landings")
    assert offer_stream["offers"] == [{"offer_id": 42, "share": 50}, {"offer_id": 43, "share": 50}]
    # Поля потока, которые Keitaro требует, сохранены при обновлении
    assert offer_stream["action_type"] == "http"
    assert offer_stream["position"] == 2


def test_add_offer_rejects_unknown_and_duplicate(client, fake):
    cid = _make_campaign_with_offers(client, fake)
    assert client.post(f"/api/campaigns/{cid}/offers", json={"offer_id": 999}).status_code == 422
    dup = client.post(f"/api/campaigns/{cid}/offers", json={"offer_id": 42})
    assert dup.status_code == 422
    assert "уже" in dup.json()["detail"]


def test_remove_offer(client, fake):
    cid = _make_campaign_with_offers(client, fake)
    client.post(f"/api/campaigns/{cid}/offers", json={"offer_id": 43})
    r = client.delete(f"/api/campaigns/{cid}/offers/42")
    assert r.status_code == 200, r.text
    assert [o["offer_id"] for o in r.json()["offers"]] == [43]


def test_cannot_remove_last_offer(client, fake):
    cid = _make_campaign_with_offers(client, fake)
    r = client.delete(f"/api/campaigns/{cid}/offers/42")
    assert r.status_code == 422
    assert "последний" in r.json()["detail"]


def test_remove_offer_not_in_campaign(client, fake):
    cid = _make_campaign_with_offers(client, fake)
    assert client.delete(f"/api/campaigns/{cid}/offers/43").status_code == 404


def test_offers_for_campaign_without_offer_stream(client, fake):
    # Кампания без потока с офферами (например, поток удалён в Keitaro)
    fake.campaigns[9] = {"id": 9, "name": "bare"}
    assert client.get("/api/campaigns/9/offers").status_code == 404


# --- Веса офферов ----------------------------------------------------------


def _offer_stream_of(fake):
    return next(s for s in fake.streams if s["schema"] == "landings")


def _shares(fake):
    return {o["offer_id"]: o["share"] for o in _offer_stream_of(fake)["offers"]}


@pytest.fixture()
def three_offers(client, fake):
    fake.offers.append({"id": 44, "name": "Third"})
    cid = _make_campaign_with_offers(client, fake)
    client.post(f"/api/campaigns/{cid}/offers", json={"offer_id": 43})
    client.post(f"/api/campaigns/{cid}/offers", json={"offer_id": 44})
    return cid


def test_three_offers_split_evenly_summing_100(three_offers, fake):
    assert sorted(_shares(fake).values()) == [33, 33, 34]
    assert sum(_shares(fake).values()) == 100


def test_pinned_weight_is_kept_when_adding_and_removing(client, fake, three_offers):
    cid = three_offers
    r = client.put(f"/api/campaigns/{cid}/offers/42/weight", json={"share": 40})
    assert r.status_code == 200, r.text
    assert _shares(fake)[42] == 40
    assert sum(_shares(fake).values()) == 100
    # Остальные делят 60% поровну
    assert sorted([_shares(fake)[43], _shares(fake)[44]]) == [30, 30]

    fake.offers.append({"id": 45, "name": "Fourth"})
    client.post(f"/api/campaigns/{cid}/offers", json={"offer_id": 45})
    assert _shares(fake)[42] == 40  # закреплённый не пересчитан
    assert sum(_shares(fake).values()) == 100

    client.delete(f"/api/campaigns/{cid}/offers/44")
    assert _shares(fake)[42] == 40
    assert sum(_shares(fake).values()) == 100


def test_unpinning_returns_to_equal_split(client, fake, three_offers):
    cid = three_offers
    client.put(f"/api/campaigns/{cid}/offers/42/weight", json={"share": 70})
    r = client.put(f"/api/campaigns/{cid}/offers/42/weight", json={"share": None})
    assert r.status_code == 200
    assert sorted(_shares(fake).values()) == [33, 33, 34]
    assert all(not o["pinned"] for o in r.json()["offers"])


def test_pins_rejected_when_free_offers_get_nothing(client, fake, three_offers):
    cid = three_offers
    client.put(f"/api/campaigns/{cid}/offers/42/weight", json={"share": 98})
    before = _shares(fake)
    r = client.put(f"/api/campaigns/{cid}/offers/43/weight", json={"share": 2})
    # 98 + 2 = 100, на оставшийся 44 места не хватает
    assert r.status_code == 422
    assert "незакреплённых" in r.json()["detail"]
    assert _shares(fake) == before  # Keitaro не изменён


def test_all_pinned_must_sum_to_100(client, fake, three_offers):
    cid = three_offers
    for oid in (42, 43):
        assert client.put(f"/api/campaigns/{cid}/offers/{oid}/weight", json={"share": 30}).status_code == 200
    r = client.put(f"/api/campaigns/{cid}/offers/44/weight", json={"share": 30})
    assert r.status_code == 422
    assert "100" in r.json()["detail"]


def test_weight_out_of_range_rejected(client, three_offers):
    cid = three_offers
    assert client.put(f"/api/campaigns/{cid}/offers/42/weight", json={"share": 0}).status_code == 422
    assert client.put(f"/api/campaigns/{cid}/offers/42/weight", json={"share": 101}).status_code == 422


def test_weight_for_offer_not_in_campaign(client, three_offers):
    assert client.put(f"/api/campaigns/{three_offers}/offers/999/weight", json={"share": 10}).status_code == 404


def test_list_shows_pinned_flag(client, fake, three_offers):
    cid = three_offers
    client.put(f"/api/campaigns/{cid}/offers/43/weight", json={"share": 20})
    data = client.get(f"/api/campaigns/{cid}/offers").json()
    by_id = {o["offer_id"]: o for o in data["offers"]}
    assert by_id[43]["pinned"] is True and by_id[43]["share"] == 20
    assert by_id[42]["pinned"] is False
    assert data["total"] == 100


# --- Несколько офферов при создании ----------------------------------------


def test_creator_with_several_offers_splits_weights(client, fake):
    fake.offers.append({"id": 44, "name": "Third"})
    r = client.post("/api/campaign-creator", json=_creator(offer_ids=[42, 43, 44]))
    assert r.status_code == 201, r.text
    offer_stream = next(s for s in fake.streams if s["schema"] == "landings")
    shares = {o["offer_id"]: o["share"] for o in offer_stream["offers"]}
    assert sorted(shares.values()) == [33, 33, 34]
    assert sum(shares.values()) == 100


def test_creator_offers_not_in_keitaro_are_listed(client, fake):
    r = client.post("/api/campaign-creator", json=_creator(offer_ids=[42, 777, 888]))
    assert r.status_code == 422
    assert "#777" in r.json()["detail"] and "#888" in r.json()["detail"]
    assert 2 not in fake.campaigns


def test_creator_pins_weight_and_saves_it(client, fake):
    r = client.post(
        "/api/campaign-creator",
        json=_creator(offer_ids=[42, 43], weights={"42": 70}),
    )
    assert r.status_code == 201, r.text
    offer_stream = next(s for s in fake.streams if s["schema"] == "landings")
    shares = {o["offer_id"]: o["share"] for o in offer_stream["offers"]}
    assert shares == {42: 70, 43: 30}
    # Закрепление сохранено, значит последующие изменения его не сбросят
    listed = client.get(f"/api/campaigns/{r.json()['campaign']['id']}/offers").json()
    assert {o["offer_id"]: o["pinned"] for o in listed["offers"]} == {42: True, 43: False}


def test_creator_rejects_impossible_weights_without_creating(client, fake):
    r = client.post(
        "/api/campaign-creator",
        json=_creator(offer_ids=[42, 43], weights={"42": 100}),
    )
    assert r.status_code == 422
    assert 2 not in fake.campaigns


def test_creator_rejects_weight_for_unknown_offer(client):
    r = client.post("/api/campaign-creator", json=_creator(offer_ids=[42], weights={"43": 10}))
    assert r.status_code == 422


def test_preview_weights(client):
    r = client.post("/api/offer-weights/preview", json={"offer_ids": [1, 2, 3], "pins": {"2": 40}})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 100
    by_id = {o["offer_id"]: o for o in data["offers"]}
    assert by_id[2] == {"offer_id": 2, "share": 40, "pinned": True}
    assert by_id[1]["share"] + by_id[3]["share"] == 60
    assert by_id[1]["pinned"] is False


def test_preview_reports_impossible_weights(client):
    r = client.post("/api/offer-weights/preview", json={"offer_ids": [1, 2], "pins": {"1": 100}})
    assert r.status_code == 422
