import json
from .models import AuditLog

def audit(db, user, action, coupon_id=None, patient_id=None, details=None):
    db.add(AuditLog(
        user=user,
        action=action,
        coupon_id=coupon_id,
        patient_id=patient_id,
        details=json.dumps(details) if details else None,
    ))
