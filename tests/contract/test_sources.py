"""The claims contract catches what the January release broke."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from llmdata.contracts import ClaimRecord, ContractError, require
from llmdata.synthetic import plan

ROW = {
    "claim_id": "CLM-00042",
    "policy_id": "POL-00017",
    "region": "north",
    "status": "open",
    "note": "Caller reported water through the kitchen ceiling.",
    "updated_at": datetime(2027, 1, 11, 9, 30, tzinfo=UTC),
}


# region: contract-test
@pytest.mark.chapter(2)
def test_a_valid_claim_passes() -> None:
    assert ClaimRecord.model_validate(ROW).region == "north"


@pytest.mark.chapter(2)
@pytest.mark.parametrize(
    "change",
    [
        {"region": ""},  # what the January release sent
        {"region": None},
        {"updated_at": datetime(2027, 1, 11, 9, 30)},  # no zone
        {"note": ""},
        {"deleted_at": datetime(2027, 1, 12, tzinfo=UTC)},
    ],
)
def test_broken_claims_fail_loudly(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(ROW | change)


@pytest.mark.chapter(2)
def test_one_bad_row_stops_the_batch() -> None:
    rows = [ROW, ROW | {"claim_id": "CLM-00043", "region": ""}]
    with pytest.raises(ContractError, match="CLM-00043 region"):
        require(ClaimRecord, rows, "claim_id")


# endregion


@pytest.mark.chapter(2)
def test_extra_columns_are_tolerated() -> None:
    assert ClaimRecord.model_validate(ROW | {"region_code": "N1"})


@pytest.mark.chapter(2)
def test_every_generated_claim_honours_the_contract() -> None:
    names = [
        "claim_id",
        "policy_id",
        "region",
        "status",
        "note",
        "updated_at",
    ]
    rows = [
        dict(zip(names, row, strict=True))
        for row in plan("full")["claims"]
    ]
    assert len(require(ClaimRecord, rows, "claim_id")) == 200
