import features.text_rules  # noqa: F401  (registers offline handler)
from llm.client import complete_json
from llm.redact import redact


def test_offline_text_features():
    out = complete_json("text_features", 1, {"text": "I got laid off last month"}, "text_features")
    assert out["hardship_signal"] == "clear"
    assert out["_meta"]["provider"] == "offline"


def test_redact():
    s = redact("Call me at 416-555-0199 or ryan@example.com, Ryan", known_names=["Ryan"])
    assert "416" not in s and "example.com" not in s and "Ryan" not in s
