"""Step 3: static-post wrapper never publishes."""

from __future__ import annotations

import pytest

from tools.weekday_cadence_config import WeekdayCadenceConfig
from tools.weekday_cadence_posts import PublishBlocked, call_make_social_post, force_no_publish


def test_config_rejects_publish_flag():
    with pytest.raises(ValueError):
        WeekdayCadenceConfig(publish_generated_media=True)


def test_force_no_publish_overrides_kwargs():
    kwargs = force_no_publish(abbr="EN", day="Monday")
    assert kwargs["publish_generated_media"] is False
    with pytest.raises(PublishBlocked):
        force_no_publish(publish_generated_media=True)


def test_make_social_post_wrapper_forces_false_and_does_not_call_publish():
    seen = {}

    def fake_make_social_post(*args, **kwargs):
        seen["kwargs"] = kwargs
        return {"folder": "unused", "ok": True}

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("publish collaborator must not be called")

    result = call_make_social_post(
        fake_make_social_post,
        "EN",
        "Monday",
        "{novel}",
        False,
        auto_publish_generated_media=should_not_run,
    )
    assert result["ok"] is True
    assert seen["kwargs"]["publish_generated_media"] is False
