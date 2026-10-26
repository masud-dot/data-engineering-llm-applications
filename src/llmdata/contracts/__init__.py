"""Data contracts shared by every stage (Chapter 2)."""

from llmdata.contracts.documents import DIMENSIONS, Chunk, Document
from llmdata.contracts.slas import Sla, load_slas
from llmdata.contracts.sources import ClaimRecord, SourceItem
from llmdata.contracts.types import (
    Access,
    DocKey,
    Kind,
    Op,
    Origin,
    Region,
    Role,
)
from llmdata.contracts.validate import (
    ContractError,
    Violation,
    require,
    validate,
)

__all__ = [
    "DIMENSIONS",
    "Access",
    "Chunk",
    "ClaimRecord",
    "ContractError",
    "DocKey",
    "Document",
    "Kind",
    "Op",
    "Origin",
    "Region",
    "Role",
    "Sla",
    "SourceItem",
    "Violation",
    "load_slas",
    "require",
    "validate",
]
