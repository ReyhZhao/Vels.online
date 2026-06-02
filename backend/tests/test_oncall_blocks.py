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
    # Should not raise
    validate_tiling()


@pytest.mark.django_db
def test_gap_in_tiling_fails():
    make_blocks(
        ("Morning", "06:00", "14:00", 1),
        # gap: 14:00-16:00 missing
        ("Afternoon", "16:00", "22:00", 2),
        ("Night", "22:00", "06:00", 3),
    )
    with pytest.raises(ValidationError):
        validate_tiling()


@pytest.mark.django_db
def test_overlap_fails():
    make_blocks(
        ("Morning", "06:00", "15:00", 1),
        ("Afternoon", "14:00", "22:00", 2),  # overlaps Morning
        ("Night", "22:00", "06:00", 3),
    )
    with pytest.raises(ValidationError):
        validate_tiling()


@pytest.mark.django_db
def test_delete_leaving_gap_fails():
    blocks = make_blocks(
        ("Morning", "06:00", "14:00", 1),
        ("Afternoon", "14:00", "22:00", 2),
        ("Night", "22:00", "06:00", 3),
    )
    block_to_delete = blocks[1]
    block_to_delete.delete()
    with pytest.raises(ValidationError):
        validate_tiling()


@pytest.mark.django_db
def test_admin_only_create(client, django_user_model):
    """Non-admin staff gets 403 on POST."""
    staff = django_user_model.objects.create_user(username="staffonly", password="pass", is_staff=True, is_superuser=False)
    client.force_login(staff)
    res = client.post(
        "/api/oncall/blocks/",
        data={"label": "Day", "start_time": "00:00", "end_time": "00:00", "order": 1},
        content_type="application/json",
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_admin_can_create_valid_block(client, django_user_model):
    """Superuser can create blocks that form valid tiling."""
    admin = django_user_model.objects.create_user(username="admin1", password="pass", is_staff=True, is_superuser=True)
    client.force_login(admin)
    # Create all three blocks at once via the API to complete the tiling
    # First two will fail tiling check; set up directly then test
    ShiftBlock.objects.create(label="Afternoon", start_time="14:00", end_time="22:00", order=2)
    ShiftBlock.objects.create(label="Night", start_time="22:00", end_time="06:00", order=3)
    # Now add Morning via API — should complete the 24h tiling
    res = client.post(
        "/api/oncall/blocks/",
        data={"label": "Morning", "start_time": "06:00", "end_time": "14:00", "order": 1},
        content_type="application/json",
    )
    assert res.status_code == 201


@pytest.mark.django_db
def test_admin_create_with_invalid_tiling_returns_400(client, django_user_model):
    """Creating a block that leaves a gap returns 400."""
    admin = django_user_model.objects.create_user(username="admin2", password="pass", is_staff=True, is_superuser=True)
    client.force_login(admin)
    res = client.post(
        "/api/oncall/blocks/",
        data={"label": "Only", "start_time": "00:00", "end_time": "12:00", "order": 1},
        content_type="application/json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_list_requires_staff(client, django_user_model):
    regular = django_user_model.objects.create_user(username="reg", password="pass", is_staff=False)
    client.force_login(regular)
    res = client.get("/api/oncall/blocks/")
    assert res.status_code == 403
