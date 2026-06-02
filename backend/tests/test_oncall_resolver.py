import datetime

import pytest
from django.utils import timezone as tz

from oncall.models import RotationTemplateSlot, ShiftBlock
from oncall.services.resolver import get_oncall_analyst


def make_3_block_setup():
    """Create a standard 3-block 24h shift setup."""
    b1 = ShiftBlock.objects.create(label="Morning", start_time="06:00", end_time="14:00", order=1)
    b2 = ShiftBlock.objects.create(label="Afternoon", start_time="14:00", end_time="22:00", order=2)
    b3 = ShiftBlock.objects.create(label="Night", start_time="22:00", end_time="06:00", order=3)
    return b1, b2, b3


@pytest.mark.django_db
def test_template_hit_returns_correct_analyst(django_user_model):
    analyst = django_user_model.objects.create_user(username="analyst1", password="pass", is_staff=True)
    b1, b2, b3 = make_3_block_setup()

    # Monday (dow=0), Morning block
    RotationTemplateSlot.objects.create(day_of_week=0, shift_block=b1, analyst=analyst)

    # Monday 09:00 UTC falls in Morning block (06:00-14:00)
    at = datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)  # Monday
    result = get_oncall_analyst(at=at)
    assert result == analyst


@pytest.mark.django_db
def test_unassigned_slot_returns_none(django_user_model):
    b1, b2, b3 = make_3_block_setup()

    # Create slot with no analyst
    RotationTemplateSlot.objects.create(day_of_week=0, shift_block=b1, analyst=None)

    at = datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)
    result = get_oncall_analyst(at=at)
    assert result is None


@pytest.mark.django_db
def test_no_slot_returns_none(django_user_model):
    b1, b2, b3 = make_3_block_setup()
    # No template slot created

    at = datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)
    result = get_oncall_analyst(at=at)
    assert result is None


@pytest.mark.django_db
def test_naive_datetime_raises():
    naive_at = datetime.datetime(2026, 6, 1, 9, 0, 0)
    with pytest.raises(ValueError):
        get_oncall_analyst(at=naive_at)


# TODO: test accepted ShiftOverride takes precedence (skip until ShiftOverride defined in #364)
# The resolver already handles it — test added in test_oncall_swap.py

@pytest.mark.django_db
def test_resolver_returns_none_when_no_blocks():
    at = datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)
    result = get_oncall_analyst(at=at)
    assert result is None
