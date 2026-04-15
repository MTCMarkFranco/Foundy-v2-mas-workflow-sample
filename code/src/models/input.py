"""Input models for the workflow."""

import re

from pydantic import BaseModel, field_validator


CLIENT_ID_PATTERN = re.compile(r"^CLT-\d{5}$")


class WorkflowInput(BaseModel):
    """Validated input for the risk assessment workflow."""

    client_id: str

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, v: str) -> str:
        if not CLIENT_ID_PATTERN.match(v):
            raise ValueError(
                f"Invalid client_id '{v}'. Expected format: CLT-XXXXX (e.g. CLT-10001)"
            )
        return v
