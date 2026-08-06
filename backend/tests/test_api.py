"""Tests for Voice Diary API — «Мой путь»."""
import pytest
import sys
import os
from datetime import datetime, timedelta, timezone

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


def test_deleted_user_token_returns_401_not_500():
    # BUG: токен живёт 30 дней, но get_current_user не проверял, что
    # пользователь ещё существует — удалённый пользователь с ещё
    # действующим токеном ловил 500 (IntegrityError) вместо 401.
    client.post("/auth/register", json={
        "phone": "9990000007", "name": "To Delete", "password": "test12345", "consent": True,
    })
    resp = client.post("/auth/login", json={"phone": "9990000007", "password": "test12345"})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.delete("/account", headers=headers)
    assert resp.status_code == 200
    # Тот же (ещё не истёкший) токен — использовать после удаления аккаунта
    resp = client.get("/entries", headers=headers)
    assert resp.status_code == 401


# ── Entries tests ──────────────────────────────────────────────

def _get_token(phone="9990000100"):
    client.post("/auth/register", json={
        "phone": phone, "name": "Entry User", "password": "test12345", "consent": True,
    })
    resp = client.post("/auth/login", json={"phone": phone, "password": "test12345"})
    return resp.json()["access_token"]


def test_transcribe_rejects_oversized_audio(monkeypatch):
    # BUG: не было лимита на размер загружаемого аудио — большой файл
    # мог нагрузить небольшой VPS (ffmpeg + faster-whisper).
    import routers.entries_router as entries_mod
    monkeypatch.setattr(entries_mod, "MAX_AUDIO_UPLOAD_BYTES", 10)
    monkeypatch.setattr(entries_mod, "local_transcribe", lambda *a, **kw: "не должно вызваться")
    monkeypatch.setattr(entries_mod, "upload_audio_to_s3", lambda *a, **kw: "не должно вызваться")

    token = _get_token("9990000112")
    resp = client.post(
        "/stt/transcribe",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.m4a", b"x" * 100, "audio/m4a")},
    )
    assert resp.status_code == 413


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


def test_create_entry_saves_audio_s3_key():
    # BUG: audio_s3_key отсутствовал в схеме DiaryEntryCreate — аудио,
    # загруженное через /stt/transcribe, никогда не привязывалось к
    # записи и навсегда оставалось "осиротевшим" в S3.
    token = _get_token("9990000108")
    resp = client.post("/entries", json={
        "transcript_text": "Запись с аудио",
        "mood": 5,
        "audio_s3_key": "audio/108/test-key.m4a",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["audio_s3_key"] == "audio/108/test-key.m4a"


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


def test_check_and_increment_usage_is_atomic():
    # BUG: check_limit()+increment_usage() отдельными шагами — TOCTOU,
    # два параллельных запроса могли оба пройти проверку раньше коммита.
    # Прямой юнит-тест на саму функцию (не через HTTP — конкурентность
    # синхронным TestClient не сымитировать, проверяем корректность границы).
    from subscription import check_and_increment_usage, get_or_create_subscription

    token = _get_token("9990000113")
    db = SessionLocal()
    # Достаём user_id из токена так же, как это делает auth.get_current_user
    from jose import jwt as jose_jwt
    from config import SECRET_KEY, ALGORITHM
    user_id = int(jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["sub"])

    from fastapi import HTTPException

    sub = get_or_create_subscription(user_id, db)
    assert sub.voice_entries_used == 0
    for _ in range(3):  # FREE_LIMITS["voice_entries"] == 3
        check_and_increment_usage(user_id, db, "voice_entries")
    db.refresh(sub)
    assert sub.voice_entries_used == 3
    with pytest.raises(HTTPException) as exc_info:
        check_and_increment_usage(user_id, db, "voice_entries")
    assert exc_info.value.status_code == 402
    db.refresh(sub)
    assert sub.voice_entries_used == 3  # не превысило лимит при отказе
    db.close()


def test_search_refunds_quota_on_ai_failure(monkeypatch):
    # Резервируем лимит перед вызовом DeepSeek — если сам вызов упал
    # (сеть, DeepSeek недоступен), квота не должна списываться.
    # raise_server_exceptions=False — TestClient по умолчанию поднимает
    # необработанные исключения заново вместо 500 (для отладки тестов),
    # реальный клиент в проде получил бы обычный Starlette-500.
    import routers.search_router as search_mod
    local_client = TestClient(app, raise_server_exceptions=False)

    async def _boom(*a, **kw):
        raise RuntimeError("DeepSeek недоступен")
    monkeypatch.setattr(search_mod, "call_deepseek_async", _boom)

    token = _get_token("9990000114")
    headers = {"Authorization": f"Bearer {token}"}
    local_client.post("/entries", json={"transcript_text": "запись для поиска", "mood": 5}, headers=headers)

    resp = local_client.post("/search", json={"query": "как дела"}, headers=headers)
    assert resp.status_code == 500

    resp = client.get("/subscription", headers=headers)
    assert resp.json()["ai_searches_used"] == 0  # квота вернулась после сбоя


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


def test_list_entries_tag_filter_with_pagination():
    # BUG: offset/limit применялись ДО фильтра по тегу — можно было
    # пропустить часть подходящих записей при постраничной подгрузке.
    token = _get_token("9990000111")
    headers = {"Authorization": f"Bearer {token}"}
    # C (новее всех) — с тегом, B — без тега, A (старее всех) — с тегом.
    client.post("/entries", json={"transcript_text": "A", "mood": 5, "tags": ["work"]}, headers=headers)
    client.post("/entries", json={"transcript_text": "B", "mood": 5, "tags": []}, headers=headers)
    client.post("/entries", json={"transcript_text": "C", "mood": 5, "tags": ["work"]}, headers=headers)
    resp = client.get("/entries?tag=work&limit=1&offset=0", headers=headers)
    assert [e["transcript_text"] for e in resp.json()] == ["C"]
    resp = client.get("/entries?tag=work&limit=1&offset=1", headers=headers)
    assert [e["transcript_text"] for e in resp.json()] == ["A"]


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
    # Реферальный бонус — дни Premium, а не деньги на баланс.
    token1 = _get_token("9990000301")
    code_resp = client.get("/referral/code", headers={"Authorization": f"Bearer {token1}"})
    code = code_resp.json()["code"]

    token2 = _get_token("9990000302")
    resp = client.post("/referral/apply", json={"code": code}, headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 200
    assert resp.json()["bonus_days"] == 10
    assert resp.json()["premium_until"] is not None

    # Оба участника реально получили Premium — не только приглашённый.
    resp1 = client.get("/subscription", headers={"Authorization": f"Bearer {token1}"})
    assert resp1.json()["plan"] == "premium"
    resp2 = client.get("/subscription", headers={"Authorization": f"Bearer {token2}"})
    assert resp2.json()["plan"] == "premium"


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
    assert data["premium_days_earned"] == 10


def test_premium_expires_and_downgrades_to_free():
    # BUG: expires_at хранился в БД, но нигде не проверялся — Premium,
    # выданный на ограниченный срок (например, за реферала), оставался бы
    # навсегда. Ленивая проверка должна понизить план при следующем обращении.
    from subscription import grant_premium_days, get_or_create_subscription

    token = _get_token("9990000306")
    from jose import jwt as jose_jwt
    from config import SECRET_KEY, ALGORITHM
    user_id = int(jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["sub"])

    db = SessionLocal()
    grant_premium_days(user_id, db, 10)
    sub = get_or_create_subscription(user_id, db)
    assert sub.plan == "premium"
    # Искусственно переносим expires_at в прошлое — как будто срок истёк.
    sub.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    db.close()

    resp = client.get("/subscription", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["plan"] == "free"  # автоматически понижен при обращении


# ── Biography tests ─────────────────────────────────────────────

def test_build_biography_context_caps_size():
    # BUG: генерация биографии слала ИИ вообще все записи без ограничения —
    # у активных "долгих" дневниководов рано или поздно превысило бы
    # контекстное окно модели. entries переданы новыми первыми (desc),
    # как их реально отдаёт запрос в generate_biography.
    from routers.biography_router import build_biography_context

    class FakeEntry:
        def __init__(self, day, text):
            self.created_at = datetime(2026, 1, day, tzinfo=timezone.utc)
            self.structured_text = text
            self.transcript_text = text

    # Каждый блок ("[дата] " + текст) занимает ~43 символа.
    entries_desc = [
        FakeEntry(3, "N" * 30),  # самая новая
        FakeEntry(2, "M" * 30),  # средняя
        FakeEntry(1, "O" * 30),  # самая старая
    ]
    context = build_biography_context(entries_desc, max_chars=90)

    assert "N" * 30 in context  # новая точно вошла
    assert "M" * 30 in context  # средняя влезла (43+43=86 <= 90)
    assert "O" * 30 not in context  # старая не влезла (86+43=129 > 90)
    assert "[Примечание: 1 более старых записей" in context  # честно сказано, что опущено
    # Хронологический порядок сохранён — средняя (старее) идёт раньше новой
    assert context.index("M" * 30) < context.index("N" * 30)


def test_biography_pdf_export_cyrillic_name():
    # BUG: Content-Disposition раньше содержал кириллицу автора напрямую —
    # HTTP-заголовки поддерживают только Latin-1, был 500 UnicodeEncodeError.
    client.post("/auth/register", json={
        "phone": "9990000400", "name": "Алмаз Уасимов", "password": "test12345", "consent": True,
    })
    resp = client.post("/auth/login", json={"phone": "9990000400", "password": "test12345"})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/biography", json={"content": "# Обо мне\nТестовая биография."}, headers=headers)
    resp = client.get("/biography/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]
    # BUG: стандартные PDF-шрифты (Helvetica) не содержат кириллицу —
    # текст показывался квадратиками. Проверяем, что в PDF реально
    # встроен шрифт с поддержкой кириллицы, а не дефолтный Helvetica.
    assert b"DejaVuSans" in resp.content
    assert b"/BaseFont/Helvetica" not in resp.content


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
    # Токен всё ещё декодируется, но пользователя больше нет — 401, а не
    # тихий пустой список (см. test_deleted_user_token_returns_401_not_500).
    resp = client.get("/entries", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_delete_account_anonymizes_audit_log_not_deletes():
    # BUG: журнал аудита стирался вместе с аккаунтом вместо анонимизации —
    # схема объявляла ondelete="SET NULL", код делал жёсткий .delete().
    token = _get_token("9990000501")
    db = SessionLocal()
    count_before = db.query(AuditLog).count()
    db.close()
    assert count_before > 0  # register + login уже что-то залогировали

    client.delete("/account", headers={"Authorization": f"Bearer {token}"})

    db = SessionLocal()
    count_after = db.query(AuditLog).count()
    anonymized = db.query(AuditLog).filter(AuditLog.user_id.is_(None)).count()
    db.close()
    assert count_after == count_before  # ничего не удалено
    assert anonymized > 0  # хотя бы что-то анонимизировано


# ── Audio retention cron job ────────────────────────────────────

def test_cleanup_old_audio_deletes_from_s3_keeps_entry(monkeypatch):
    # Политика конфиденциальности обещает автоудаление аудио через
    # AUDIO_RETENTION_DAYS — раньше в коде не было ни одной cron-задачи,
    # которая бы это делала. Текст записи должен остаться, удаляется
    # только S3-объект + обнуляется audio_s3_key.
    import cleanup_old_audio as cleanup_mod

    token = _get_token("9990000600")
    resp = client.post("/entries", json={
        "transcript_text": "Старая запись с аудио", "mood": 5,
        "audio_s3_key": "audio/600/old.m4a",
    }, headers={"Authorization": f"Bearer {token}"})
    entry_id = resp.json()["id"]

    # created_at выставляем в прошлое напрямую в БД — через API это не задать.
    db = SessionLocal()
    old_date = datetime.now(timezone.utc) - timedelta(days=cleanup_mod.AUDIO_RETENTION_DAYS + 1)
    db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).update({"created_at": old_date})
    db.commit()
    db.close()

    deleted_keys = []
    monkeypatch.setattr(cleanup_mod, "get_s3", lambda: True)
    monkeypatch.setattr(cleanup_mod, "delete_audio_from_s3", lambda key: deleted_keys.append(key))

    count = cleanup_mod.cleanup_old_audio()

    assert count == 1
    assert deleted_keys == ["audio/600/old.m4a"]
    db = SessionLocal()
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    db.close()
    assert entry is not None  # текст остался
    assert entry.transcript_text == "Старая запись с аудио"
    assert entry.audio_s3_key is None  # аудио отвязано
