"""Tests for Voice Diary API — «Мой путь»."""
import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from database import engine, Base, SessionLocal
from models import User, Subscription, DiaryEntry, DiaryBiography, AuditLog, Referral

# Create test DB
Base.metadata.create_all(bind=engine)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    """Clean DB before each test."""
    db = SessionLocal()
    for table in [Referral, AuditLog, DiaryBiography, DiaryEntry, Subscription, User]:
        db.query(table).delete()
    db.commit()
    db.close()
    yield


# ── Auth tests ─────────────────────────────────────────────────

def test_register():
    resp = client.post("/auth/register", json={
        "phone": "9990000001",
        "name": "Test User",
        "password": "test12345",
        "consent": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user_id"] == 1
    assert data["name"] == "Test User"
    assert data["plan"] == "free"


def test_register_rejects_invalid_phone():
    resp = client.post("/auth/register", json={
        "phone": "abc-not-a-phone",
        "name": "Test User",
        "password": "test12345",
        "consent": True,
    })
    assert resp.status_code == 400
    assert "телефон" in resp.json()["detail"].lower()


def test_register_rejects_short_password():
    resp = client.post("/auth/register", json={
        "phone": "9990000006",
        "name": "Test User",
        "password": "short1",
        "consent": True,
    })
    assert resp.status_code == 400
    assert "пароль" in resp.json()["detail"].lower()


def test_register_no_consent():
    resp = client.post("/auth/register", json={
        "phone": "9990000002",
        "name": "No Consent",
        "password": "test12345",
        "consent": False,
    })
    assert resp.status_code == 400


def test_register_duplicate():
    client.post("/auth/register", json={
        "phone": "9990000003", "name": "First", "password": "test12345", "consent": True,
    })
    resp = client.post("/auth/register", json={
        "phone": "9990000003", "name": "Second", "password": "test12345", "consent": True,
    })
    assert resp.status_code == 400


def test_login():
    client.post("/auth/register", json={
        "phone": "9990000004", "name": "Login User", "password": "test12345", "consent": True,
    })
    resp = client.post("/auth/login", json={
        "phone": "9990000004", "password": "test12345",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["name"] == "Login User"


def test_login_wrong_password():
    client.post("/auth/register", json={
        "phone": "9990000005", "name": "Wrong PW", "password": "test12345", "consent": True,
    })
    resp = client.post("/auth/login", json={
        "phone": "9990000005", "password": "wrong",
    })
    assert resp.status_code == 401


def test_unauthorized():
    resp = client.get("/entries")
    assert resp.status_code == 401


# ── Entries tests ──────────────────────────────────────────────

def _get_token(phone="9990000100"):
    client.post("/auth/register", json={
        "phone": phone, "name": "Entry User", "password": "test12345", "consent": True,
    })
    resp = client.post("/auth/login", json={"phone": phone, "password": "test12345"})
    return resp.json()["access_token"]


def test_create_entry():
    token = _get_token("9990000101")
    resp = client.post("/entries", json={
        "transcript_text": "Сегодня был хороший день",
        "mood": 8,
        "tags": ["семья", "здоровье"],
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mood"] == 8
    assert "семья" in data["tags"]


def test_create_entry_enforces_free_limit():
    # SECURITY: POST /entries раньше не проверял лимит voice_entries вообще —
    # можно было создавать записи напрямую, минуя /stt/transcribe.
    token = _get_token("9990000109")
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(3):
        resp = client.post("/entries", json={
            "transcript_text": f"Запись {i}", "mood": 5,
        }, headers=headers)
        assert resp.status_code == 200
    # 4-я запись сверх бесплатного лимита (3) должна быть отклонена
    resp = client.post("/entries", json={
        "transcript_text": "Запись сверх лимита", "mood": 5,
    }, headers=headers)
    assert resp.status_code == 402


def test_process_entry_enforces_free_limit():
    # SECURITY: /entries/process (вызов DeepSeek) раньше был вообще без лимита.
    token = _get_token("9990000110")
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(3):
        client.post("/entries", json={
            "transcript_text": f"Запись {i}", "mood": 5,
        }, headers=headers)
    resp = client.post("/entries/process", json={"text": "текст"}, headers=headers)
    assert resp.status_code == 402


def test_list_entries():
    token = _get_token("9990000102")
    client.post("/entries", json={
        "transcript_text": "Запись 1", "mood": 5,
    }, headers={"Authorization": f"Bearer {token}"})
    client.post("/entries", json={
        "transcript_text": "Запись 2", "mood": 7,
    }, headers={"Authorization": f"Bearer {token}"})
    resp = client.get("/entries", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_get_entry():
    token = _get_token("9990000103")
    create_resp = client.post("/entries", json={
        "transcript_text": "Моя запись", "mood": 6,
    }, headers={"Authorization": f"Bearer {token}"})
    entry_id = create_resp.json()["id"]
    resp = client.get(f"/entries/{entry_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["transcript_text"] == "Моя запись"


def test_update_entry():
    token = _get_token("9990000104")
    create_resp = client.post("/entries", json={
        "transcript_text": "Старый текст", "mood": 3,
    }, headers={"Authorization": f"Bearer {token}"})
    entry_id = create_resp.json()["id"]
    resp = client.put(f"/entries/{entry_id}", json={
        "transcript_text": "Новый текст", "mood": 9,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["transcript_text"] == "Новый текст"
    assert resp.json()["mood"] == 9


def test_delete_entry():
    token = _get_token("9990000105")
    create_resp = client.post("/entries", json={
        "transcript_text": "Удаляемая запись", "mood": 4,
    }, headers={"Authorization": f"Bearer {token}"})
    entry_id = create_resp.json()["id"]
    resp = client.delete(f"/entries/{entry_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    # Verify gone
    resp = client.get(f"/entries/{entry_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ── Subscription tests ─────────────────────────────────────────

def test_subscription_default():
    token = _get_token("9990000200")
    resp = client.get("/subscription", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "free"
    assert data["voice_entries_limit"] == 3


def test_subscription_upgrade_not_available_without_payment():
    # Оплата ещё не подключена — ручка не должна выдавать Premium бесплатно.
    token = _get_token("9990000201")
    resp = client.post("/subscription/upgrade", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 501
    # Verify plan stayed free
    resp = client.get("/subscription", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["plan"] == "free"


# ── Referral tests ─────────────────────────────────────────────

def test_referral_code():
    token = _get_token("9990000300")
    resp = client.get("/referral/code", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "code" in resp.json()
    assert len(resp.json()["code"]) >= 6


def test_referral_apply():
    # User 1 gets code
    token1 = _get_token("9990000301")
    code_resp = client.get("/referral/code", headers={"Authorization": f"Bearer {token1}"})
    code = code_resp.json()["code"]

    # User 2 applies it
    token2 = _get_token("9990000302")
    resp = client.post("/referral/apply", json={"code": code}, headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 200
    assert resp.json()["bonus"] == 300
    assert resp.json()["balance"] == 300


def test_referral_self_apply():
    token = _get_token("9990000303")
    code_resp = client.get("/referral/code", headers={"Authorization": f"Bearer {token}"})
    code = code_resp.json()["code"]
    resp = client.post("/referral/apply", json={"code": code}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


def test_referral_stats():
    token1 = _get_token("9990000304")
    code_resp = client.get("/referral/code", headers={"Authorization": f"Bearer {token1}"})
    code = code_resp.json()["code"]

    token2 = _get_token("9990000305")
    client.post("/referral/apply", json={"code": code}, headers={"Authorization": f"Bearer {token2}"})

    resp = client.get("/referral/stats", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["invited_count"] == 1
    assert data["balance"] == 300


# ── Stats / Health tests ───────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["app"] == "Мой путь"


def test_app_version():
    resp = client.get("/app/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "version_code" in data


def test_privacy():
    resp = client.get("/privacy")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sections"]) == 6


def test_stats():
    token = _get_token("9990000400")
    client.post("/entries", json={
        "transcript_text": "Запись для статистики", "mood": 7, "tags": ["бизнес"],
    }, headers={"Authorization": f"Bearer {token}"})
    resp = client.get("/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 1
    assert data["avg_mood"] == 7.0


# ── Account deletion test ──────────────────────────────────────

def test_delete_account():
    token = _get_token("9990000500")
    client.post("/entries", json={
        "transcript_text": "Запись перед удалением", "mood": 5,
    }, headers={"Authorization": f"Bearer {token}"})
    resp = client.delete("/account", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    # Token still decodes but user's entries are gone → empty list
    resp = client.get("/entries", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []
