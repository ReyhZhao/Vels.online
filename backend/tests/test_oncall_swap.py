import datetime

import pytest

from oncall.models import RotationTemplateSlot, ShiftBlock, ShiftOverride
from oncall.services.resolver import get_oncall_analyst
from oncall.services.swap import accept_override, decline_override, request_swap


def make_3_block_setup():
    b1 = ShiftBlock.objects.create(label="Morning", start_time="06:00", end_time="14:00", order=1)
    b2 = ShiftBlock.objects.create(label="Afternoon", start_time="14:00", end_time="22:00", order=2)
    b3 = ShiftBlock.objects.create(label="Night", start_time="22:00", end_time="06:00", order=3)
    return b1, b2, b3


@pytest.mark.django_db
def test_full_swap_lifecycle(django_user_model):
    analyst1 = django_user_model.objects.create_user(username="analyst1", password="pass", is_staff=True)
    analyst2 = django_user_model.objects.create_user(username="analyst2", password="pass", is_staff=True)
    b1, _, _ = make_3_block_setup()

    override = request_swap(
        date=datetime.date(2026, 6, 1),
        shift_block=b1,
        original_analyst=analyst1,
        override_analyst=analyst2,
        initiated_by=analyst1,
        note="Need a day off",
        kind="swap",
    )
    assert override.status == ShiftOverride.STATUS_PENDING
    assert override.kind == ShiftOverride.KIND_SWAP

    accepted = accept_override(override, actor=analyst2)
    assert accepted.status == ShiftOverride.STATUS_ACCEPTED
    assert accepted.resolved_at is not None


@pytest.mark.django_db
def test_cover_offer_lifecycle_decline(django_user_model):
    analyst1 = django_user_model.objects.create_user(username="coverer1", password="pass", is_staff=True)
    analyst2 = django_user_model.objects.create_user(username="coverer2", password="pass", is_staff=True)
    b1, _, _ = make_3_block_setup()

    override = request_swap(
        date=datetime.date(2026, 6, 2),
        shift_block=b1,
        original_analyst=analyst1,
        override_analyst=analyst2,
        initiated_by=analyst2,
        note="Covering for you",
        kind="cover_offer",
    )
    assert override.kind == ShiftOverride.KIND_COVER_OFFER

    declined = decline_override(override, actor=analyst2)
    assert declined.status == ShiftOverride.STATUS_DECLINED
    assert declined.resolved_at is not None


@pytest.mark.django_db
def test_invalid_actor_raises_value_error(django_user_model):
    analyst1 = django_user_model.objects.create_user(username="act1", password="pass", is_staff=True)
    analyst2 = django_user_model.objects.create_user(username="act2", password="pass", is_staff=True)
    wrong_actor = django_user_model.objects.create_user(username="wrongactor", password="pass", is_staff=True)
    b1, _, _ = make_3_block_setup()

    override = request_swap(
        date=datetime.date(2026, 6, 3),
        shift_block=b1,
        original_analyst=analyst1,
        override_analyst=analyst2,
        initiated_by=analyst1,
    )
    with pytest.raises(ValueError, match="Only the override analyst"):
        accept_override(override, actor=wrong_actor)


@pytest.mark.django_db
def test_already_resolved_override_raises(django_user_model):
    analyst1 = django_user_model.objects.create_user(username="res1", password="pass", is_staff=True)
    analyst2 = django_user_model.objects.create_user(username="res2", password="pass", is_staff=True)
    b1, _, _ = make_3_block_setup()

    override = request_swap(
        date=datetime.date(2026, 6, 4),
        shift_block=b1,
        original_analyst=analyst1,
        override_analyst=analyst2,
        initiated_by=analyst1,
    )
    accept_override(override, actor=analyst2)

    with pytest.raises(ValueError, match="Cannot accept"):
        accept_override(override, actor=analyst2)


@pytest.mark.django_db
def test_accepted_override_takes_precedence_over_template(django_user_model):
    """Resolver should return override_analyst when an accepted override exists."""
    template_analyst = django_user_model.objects.create_user(username="template_a", password="pass", is_staff=True)
    swap_analyst = django_user_model.objects.create_user(username="swap_a", password="pass", is_staff=True)
    b1, _, _ = make_3_block_setup()

    # Set up template slot for Monday
    RotationTemplateSlot.objects.create(day_of_week=0, shift_block=b1, analyst=template_analyst)

    # Create and accept a swap for 2026-06-01 (Monday) Morning block
    at = datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)
    override = request_swap(
        date=at.date(),
        shift_block=b1,
        original_analyst=template_analyst,
        override_analyst=swap_analyst,
        initiated_by=template_analyst,
    )
    accept_override(override, actor=swap_analyst)

    result = get_oncall_analyst(at=at)
    assert result == swap_analyst


@pytest.mark.django_db
def test_pending_override_does_not_take_precedence(django_user_model):
    """A pending override should NOT change who is on call."""
    template_analyst = django_user_model.objects.create_user(username="tmpl_b", password="pass", is_staff=True)
    swap_analyst = django_user_model.objects.create_user(username="swap_b", password="pass", is_staff=True)
    b1, _, _ = make_3_block_setup()

    RotationTemplateSlot.objects.create(day_of_week=0, shift_block=b1, analyst=template_analyst)

    at = datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)
    # Only request, not accept
    request_swap(
        date=at.date(),
        shift_block=b1,
        original_analyst=template_analyst,
        override_analyst=swap_analyst,
        initiated_by=template_analyst,
    )

    result = get_oncall_analyst(at=at)
    assert result == template_analyst  # template still applies
