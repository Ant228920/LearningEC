from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# --- Завдання 2: Personal Data Export ---

class UserProfileExport(BaseModel):
    user_id: int
    email: str
    username: str
    phone: Optional[str] = None


class UserActivityExport(BaseModel):
    action: str
    timestamp: datetime
    details: Dict[str, Any] = {}


class ConsentExport(BaseModel):
    purpose: str
    is_granted: bool
    policy_version: str
    updated_at: datetime


class PersonalDataExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    export_metadata: Dict[str, str]
    subject_id: int
    profile: UserProfileExport
    activity_history: List[UserActivityExport] = []
    consents: List[ConsentExport] = []


# --- Завдання 3: Right to Erasure / Anonymization ---

class AnonymizeResponse(BaseModel):
    status: str
    message: str
    user_id: int
    anonymized_at: str


# --- Завдання 4: Consent Management Engine ---

class ConsentPurpose(str, Enum):
    MARKETING_EMAIL = "MARKETING_EMAIL"
    OPTIONAL_ANALYTICS = "OPTIONAL_ANALYTICS"


class ConsentUpdateRequest(BaseModel):
    purpose: ConsentPurpose
    policy_version: str = Field(default="v1.0")


class ConsentActionResponse(BaseModel):
    user_id: int
    purpose: ConsentPurpose
    is_granted: bool
    policy_version: str
    updated_at: str


class MarketingCampaignRequest(BaseModel):
    campaign_name: str
    message: str