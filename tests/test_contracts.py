from insurance_platform.contracts import compare_contract_metadata


def test_source_contract_accepts_declared_additive_columns():
    contract = {
        "source_table": "claims",
        "primary_key": "claim_id",
        "allow_additive_columns": True,
        "columns": {
            "claim_id": {"data_type": "text", "nullable": False},
            "updated_at": {
                "data_type": "timestamp with time zone",
                "nullable": False,
            },
        },
    }
    observed = {
        "claim_id": ("text", False),
        "updated_at": ("timestamp with time zone", False),
        "submission_channel": ("text", True),
    }

    result = compare_contract_metadata(contract, observed, {"claim_id"})

    assert result.is_valid
    assert result.additive_columns == ("submission_channel",)


def test_source_contract_rejects_breaking_type_change():
    contract = {
        "source_table": "claims",
        "primary_key": "claim_id",
        "allow_additive_columns": True,
        "columns": {
            "claim_id": {"data_type": "text", "nullable": False},
            "claim_amount": {"data_type": "numeric", "nullable": False},
        },
    }
    observed = {
        "claim_id": ("text", False),
        "claim_amount": ("text", False),
    }

    result = compare_contract_metadata(contract, observed, {"claim_id"})

    assert not result.is_valid
    assert any("type mismatch for claim_amount" in error for error in result.errors)


def test_source_contract_rejects_primary_key_change():
    contract = {
        "source_table": "claims",
        "primary_key": "claim_id",
        "allow_additive_columns": True,
        "columns": {
            "claim_id": {"data_type": "text", "nullable": False},
        },
    }

    result = compare_contract_metadata(
        contract,
        {"claim_id": ("text", False)},
        {"policy_id"},
    )

    assert not result.is_valid
    assert any("primary-key mismatch" in error for error in result.errors)
