import pytest
from django.core.exceptions import ValidationError

from oncall.models import ShiftBlock, validate_tiling


def make_blocks(*specs):
    """Create ShiftBlock instances from (label, start, end, order) specs."""
    blocks = []
    for label, start, end, order in specs:
        b = ShiftBlock.objects.create(label=label, start_time=start, end_time=end, order=order)
        blocks.append(b)
    return blocks


@pytest.mark.django_db
def test_valid_3block_24h_tiling_passes():
    make_blocks(
        ("Morning", "06:00", "14:00", 1),
        ("Afternoon", "14:00", "22:00", 2),
        ("Night", "22:00", "06:00", 3),
    )
    validate_tiling()


@pytest.mark.django_db
def test_gap_in_tiling_is_allowed():
    """Gaps between blocks are allowed — partial coverage is valid."""
    make_blocks(
        ("Morning", "06:00", "14:00", 1),
        # gap: 14:00-16:00 uncovered — this is intentional
        ("Afternoon", "16:00", "22:00", 2),
    )
    validate_tiling()  # should not raise


@pytest.mark.django_db
def test_single_partial_block_is_allowed():
    """A single block covering less than 24h is valid."""
    make_blocks(("Day", "08:00", "20:00", 1))
    validate_tiling()  # should not raise


@pytest.mark.django_db
def test_large_block_without_overlap_is_allowed():
    """A large block that doesn't overlap another is valid."""
    make_blocks(
        ("Day", "06:00", "22:00", 1),   # 16h, does not cover midnight
        ("Extra", "04:00", "06:00", 2), # 2h, adjacent to Day with no overlap
    )
    validate_tiling()  # should not raise


@pytest.mark.django_db
def test_overlap_fails():
    make_blocks(
        ("Morning", "06:00", "15:00", 1),
        ("Afternoon", "14:00", "22:00", 2),  # overlaps Morning 14:00-15:00
        ("Night", "22:00", "06:00", 3),
    )
    with pytest.raises(ValidationError, match="overlap"):
        validate_tiling()


@pytest.mark.django_db
def test_midnight_crossing_overlap_fails():
    """A midnight-crossing block must not overlap another block."""
    make_blocks(
        ("Night", "22:00", "08:00", 1),   # covers 22:00-08:00
        ("Morning", "06:00", "14:00", 2), # covers 06:00-14:00 — overlaps Night 06:00-08:00
    )
    with pytest.raises(ValidationError, match="overlap"):
        validate_tiling()


@pytest.mark.django_db
def test_delete_leaving_gap_is_allowed(client):
    """Deleting a block that leaves a gap is valid — gaps are OK."""
    blocks = make_blocks(
        ("Morning", "06:00", "14:00", 1),
        ("Afternoon", "14:00", "22:00", 2),
        ("Night", "22:00", "06:00", 3),
    )
    block_to_delete = blocks[1]
    block_to_delete.delete()
    validate_tiling()  # should not raise


@pytest.mark.django_db
def test_non_staff_create_gets_403(client, django_user_model):
    """Non-staff user gets 403 on POST."""
    regular = django_user_model.objects.create_user(username="notstaff", password="pass", is_staff=False)
    client.force_login(regular)
    res = client.post(
        "/api/oncall/blocks/",
        data={"label": "Day", "start_time": "00:00", "end_time": "00:00", "order": 1},
        content_type="application/json",
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_staff_can_create_valid_block(client, django_user_model):
    """Any staff user can create blocks that form valid tiling."""
    staff = django_user_model.objects.create_user(username="staff1", password="pass", is_staff=True)
    client.force_login(staff)
    ShiftBlock.objects.create(label="Afternoon", start_time="14:00", end_time="22:00", order=2)
    ShiftBlock.objects.create(label="Night", start_time="22:00", end_time="06:00", order=3)
    res = client.post(
        "/api/oncall/blocks/",
        data={"label": "Morning", "start_time": "06:00", "end_time": "14:00", "order": 1},
        content_type="application/json",
    )
    assert res.status_code == 201


@pytest.mark.django_db
def test_staff_can_create_partial_block(client, django_user_model):
    """Creating a block that doesn't cover 24h is now valid."""
    staff = django_user_model.objects.create_user(username="staff2", password="pass", is_staff=True)
    client.force_login(staff)
    res = client.post(
        "/api/oncall/blocks/",
        data={"label": "Only", "start_time": "00:00", "end_time": "12:00", "order": 1},
        content_type="application/json",
    )
    assert res.status_code == 201


@pytest.mark.django_db
def test_staff_create_overlapping_block_returns_400(client, django_user_model):
    """Creating a block that overlaps an existing one returns 400."""
    staff = django_user_model.objects.create_user(username="staff3", password="pass", is_staff=True)
    client.force_login(staff)
    ShiftBlock.objects.create(label="Existing", start_time="08:00", end_time="16:00", order=1)
    res = client.post(
        "/api/oncall/blocks/",
        data={"label": "Overlap", "start_time": "12:00", "end_time": "20:00", "order": 2},
        content_type="application/json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_list_requires_staff(client, django_user_model):
    regular = django_user_model.objects.create_user(username="reg", password="pass", is_staff=False)
    client.force_login(regular)
    res = client.get("/api/oncall/blocks/")
    assert res.status_code == 403
