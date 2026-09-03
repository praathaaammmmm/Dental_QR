import re

from pydantic import BaseModel, EmailStr, Field, field_validator

class PatientCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    mobile: str = Field(min_length=5, max_length=30)
    email: EmailStr | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = Field(default=None, max_length=30)
    city: str | None = Field(default=None, max_length=100)
    doctor_name: str | None = Field(default=None, max_length=150)
    campaign_name: str | None = Field(default=None, max_length=150)
    offer_id: int = Field(gt=0)
    consent_given: bool

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value):
        value = " ".join(value.split())
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("Enter a valid name")
        return value

    @field_validator("mobile")
    @classmethod
    def clean_mobile(cls, v):
        value = re.sub(r"[\s()-]", "", v)
        if not re.fullmatch(r"\+?\d{7,15}", value):
            raise ValueError("Enter a valid mobile number")
        return value

    @field_validator("gender", "city", "doctor_name", "campaign_name", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        if value is None:
            return None
        cleaned = " ".join(str(value).split())
        return cleaned or None
