"""Audit logging (152-ФЗ compliance)."""
import logging
from sqlalchemy.orm import Session
from models import AuditLog

logger = logging.getLogger("voice-diary")


def audit_log(db: Session, user_id: int, action: str, ip: str = "", details: str = ""):
    try:
        log = AuditLog(user_id=user_id, action=action, ip_address=ip, details=details)
        db.add(log)
        db.commit()
        logger.info(f"AUDIT user={user_id} action={action} ip={ip}")
    except Exception as e:
        logger.error(f"Audit log failed: {e}")
