import pytest
from utils.nlp.parser import parse_multiple_intents

aliases = {"me": "ronnie", "erica": "erica", "becky": "becky"}

@pytest.mark.parametrize("text, expected", [
    (
        "Add laundry to Erica due tomorrow",
        [("add", {"chore": "laundry", "assignee": "erica"})],
    ),
    (
        "Add dishes and vacuuming to me every Saturday",
        [
            ("add", {"chore": "dishes", "assignee": "ronnie", "recurrence": "weekly (Saturday)"}),
            ("add", {"chore": "vacuuming", "assignee": "ronnie", "recurrence": "weekly (Saturday)"}),
        ],
    ),
    (
        "List chores then mark it done",
        [("list", {}), ("done", {})],
    ),
    (
        "Add laundry and delete dishes",
        [
            ("add", {"chore": "laundry", "assignee": "ronnie"}),
            ("delete", {"chore": "dishes"}),
        ],
    ),
])
def test_parse_intents(text, expected):
    results = parse_multiple_intents(text, sender="ronnie", aliases=aliases)
    assert len(results) == len(expected), f"Expected {len(expected)} intents, got {len(results)} for: {text}"
    for (intent, entities), (expected_intent, expected_entities) in zip(results, expected):
        assert intent == expected_intent, f"Expected intent '{expected_intent}' but got '{intent}' for: {text}"
        for key, val in expected_entities.items():
            assert key in entities, f"Missing entity '{key}' in {entities}"
            if key == "due_date":
                assert isinstance(entities[key], type(val))  # allow fuzzy datetime match
            else:
                assert entities[key] == val, f"Expected {key}='{val}', got '{entities[key]}'"


@pytest.mark.parametrize("text, expected_recurrence", [
    ("Add recycling to me every Monday and Thursday", "weekly (Monday, Thursday)"),
    ("Add trash to me every day", "daily"),
    ("Add sweeping every weekend", "weekends"),
])
def test_recurrence_parsing(text, expected_recurrence):
    results = parse_multiple_intents(text, sender="ronnie", aliases=aliases)
    assert results, "No intents parsed"
    recurrence = results[0][1].get("recurrence")
    assert recurrence, f"No recurrence found in: {text}"
    assert expected_recurrence in recurrence


@pytest.mark.parametrize("text", [
    "do it",
    "mark it done",
    "delete it",
    "remind her tomorrow",
    "assign it to Becky",
    "postpone it to next week",
])
def test_follow_up_intents(text):
    results = parse_multiple_intents(text, sender="ronnie", aliases=aliases)
    assert results, f"No result for: {text}"
    assert results[0][0] == "follow_up", f"Expected 'follow_up' but got '{results[0][0]}'"