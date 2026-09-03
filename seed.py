from datetime import timedelta
from app.database import Base, engine, SessionLocal
from app.time_utils import utc_now
from app.models import Patient, Offer, PatientOffer
from app.qr_service import new_uid, expiry_for, generate_qr, token_for, token_hash

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    crown = db.query(Offer).filter(Offer.name == "Free In-House Zirconia Crown").first()
    aligner = db.query(Offer).filter(Offer.name == "Free In-House Aligner Scan").first()
    samples = [("Rahul Sharma", "9800000001", crown), ("Amit Kumar", "9800000002", aligner), ("Neha Singh", "9800000003", crown)]
    for name, mobile, offer in samples:
        now = utc_now(); week = (now - timedelta(days=(now.weekday() + 1) % 7)).date()
        p = Patient(patient_uid=new_uid("PAT"), full_name=name, mobile=mobile, city="Test City", campaign_name="DEVELOPMENT TEST DATA", registration_week=week, consent_given=True, consent_version="development", consented_at=now, created_at=now)
        db.add(p); db.flush()
        uid = new_uid("SRD"); token = token_for(uid)
        c = PatientOffer(coupon_uid=uid, patient_id=p.id, offer_id=offer.id, secure_token_hash=token_hash(token), created_at=now, expires_at=expiry_for(now), status="ACTIVE")
        db.add(c); db.flush(); generate_qr(token, c.coupon_uid)
    db.commit()
    print("Development seed complete: Rahul Sharma, Amit Kumar, Neha Singh")
finally:
    db.close()
