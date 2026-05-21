def auto_link_contacts_for_asset(incident, asset):
    from contacts.models import AssetOwner, IncidentContact

    owner_contact_ids = AssetOwner.objects.filter(asset=asset).values_list("contact_id", flat=True)
    for contact_id in owner_contact_ids:
        IncidentContact.objects.get_or_create(
            incident=incident,
            contact_id=contact_id,
            defaults={"role": IncidentContact.ROLE_NOTIFIED},
        )
