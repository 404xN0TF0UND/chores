
# tests/test_follow_up.py

import pytest
from datetime import datetime, timedelta
from utils.context.context_utils import ContextTracker
from utils.context.follow_up import resolve_follow_up


@pytest.fixture
def context():
    ctx = ContextTracker()
    ctx.last_intent = "add"
    ctx.last_chore = "dishes"
    ctx.last_assignee = "erica"
    ctx.last_due_date = datetime.now() + timedelta(days=1)
    return ctx

@pytest.mark.parametrize("message,expected_intent,expected_entities", [
    ("do it", "done", {"chore": "dishes"}),
    ("mark it done", "done", {"chore": "dishes"}),
    ("delete it", "delete", {"chore": "dishes"}),
    ("assign it to Becky", "add", {"chore": "dishes", "assignee": "becky"}),
    ("remind her tomorrow", "add", {"chore": "dishes", "assignee": "erica", "due_date": "future"}),
    ("postpone it to next week", "add", {"chore": "dishes", "due_date": "future"}),
])
def test_resolve_follow_up(message, expected_intent, expected_entities, context):
    intent, entities = resolve_follow_up(message, context, sender="ronnie")

    assert intent == expected_intent, f"Expected intent '{expected_intent}', got '{intent}'"
    for key, expected_val in expected_entities.items():
        assert key in entities, f"Missing entity '{key}' in {entities}"
        if key == "due_date":
            assert isinstance(entities[key], datetime), f"due_date should be datetime, got {type(entities[key])}"
            assert entities[key] > datetime.now(), f"due_date not in the future: {entities[key]}"
        else:
            assert entities[key].lower() == expected_val.lower()