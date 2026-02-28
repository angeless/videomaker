"""Shared types for product capability modules."""

from dataclasses import dataclass, field
from typing import List, Literal


CapabilityStatus = Literal["ready", "prototype", "planned"]


@dataclass(frozen=True)
class CapabilitySpec:
    """Static definition of a product capability boundary."""

    capability_id: str
    name: str
    goal: str
    inputs: List[str]
    outputs: List[str]
    depends_on: List[str] = field(default_factory=list)
    status: CapabilityStatus = "planned"
    references: List[str] = field(default_factory=list)
