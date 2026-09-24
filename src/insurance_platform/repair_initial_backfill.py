"""Backward-compatible entrypoint for the former initial-backfill command.

The implementation now performs full current-state version reconciliation rather than
checking only whether a primary key exists in RAW.
"""

from insurance_platform.reconcile_source_state import run


if __name__ == "__main__":
    run()
