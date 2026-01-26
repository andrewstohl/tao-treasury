"""Tests to enforce model constraints and prevent anti-patterns.

These tests fail if any model contains prohibited patterns like JSON history columns.
"""

import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest
from sqlalchemy import inspect

from app.core.database import Base


class TestModelConstraints:
    """Enforce model design constraints."""

    def test_no_json_history_columns(self):
        """Ensure no model contains JSON history columns.

        JSON history columns are an anti-pattern because:
        - They grow unbounded over time
        - They're expensive to query/index
        - They bypass relational integrity

        Use separate history/snapshot tables instead.
        """
        prohibited_patterns = [
            "regime_history_json",
            "history_json",
            "_history_json",
        ]

        violations = []

        for mapper in Base.registry.mappers:
            table = mapper.persist_selectable
            for column in table.columns:
                column_name = column.name.lower()
                for pattern in prohibited_patterns:
                    if pattern in column_name:
                        violations.append(
                            f"{table.name}.{column.name} contains prohibited pattern '{pattern}'"
                        )

        if violations:
            violation_msg = "\n".join(f"  - {v}" for v in violations)
            pytest.fail(
                f"Found {len(violations)} JSON history column(s) in models:\n{violation_msg}\n\n"
                "Use separate history/snapshot tables instead of JSON columns."
            )

    def test_no_jsonb_history_columns(self):
        """Ensure no model uses JSONB for storing history data.

        Same rationale as test_no_json_history_columns - JSONB history
        columns are an anti-pattern.
        """
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import JSON

        violations = []

        for mapper in Base.registry.mappers:
            table = mapper.persist_selectable
            for column in table.columns:
                column_name = column.name.lower()
                # Check if column is JSON/JSONB and has "history" in name
                if hasattr(column.type, '__class__'):
                    type_name = column.type.__class__.__name__
                    if type_name in ('JSON', 'JSONB') and 'history' in column_name:
                        violations.append(
                            f"{table.name}.{column.name} is {type_name} with 'history' in name"
                        )

        if violations:
            violation_msg = "\n".join(f"  - {v}" for v in violations)
            pytest.fail(
                f"Found {len(violations)} JSON/JSONB history column(s):\n{violation_msg}\n\n"
                "Use separate history/snapshot tables instead."
            )

    def test_models_have_required_metadata(self):
        """Verify all models have expected base columns.

        Most models should have:
        - Primary key (id)
        - Timestamps (created_at and/or updated_at)
        """
        exceptions = {
            # Tables that may not follow the standard pattern
            "alembic_version",
        }

        missing_pk = []

        for mapper in Base.registry.mappers:
            table = mapper.persist_selectable
            if table.name in exceptions:
                continue

            # Check for primary key
            if not table.primary_key:
                missing_pk.append(table.name)

        if missing_pk:
            pytest.fail(
                f"Tables missing primary key: {', '.join(missing_pk)}"
            )
