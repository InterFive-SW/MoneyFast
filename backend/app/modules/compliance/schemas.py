"""Request/response models for POST /api/compliance/validate."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ComplianceRequest(BaseModel):
    draft_response: str
    user_query: str
    jurisdiction: str = "TR"
    tools_used: List[str] = Field(default_factory=list)
    contains_personal_data: bool = False
    contains_transaction_proposal: bool = False
    # There is no permissive mode by design. STANDARD is the floor.
    strictness: Literal["STANDARD", "STRICT"] = "STANDARD"


class ComplianceResponse(BaseModel):
    verdict: Literal["PASS", "REVISE", "BLOCK"]
    rule_pack_version: str
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    required_disclosures: List[Dict[str, str]] = Field(default_factory=list)
    remediated_response: Optional[str] = None
    blocked_reason_user_facing: Optional[str] = None
    audit_id: str
