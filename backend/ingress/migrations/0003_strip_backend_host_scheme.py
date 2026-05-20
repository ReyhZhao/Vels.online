from django.db import migrations


def strip_scheme(apps, schema_editor):
    Route = apps.get_model("ingress", "Route")
    for route in Route.objects.filter(backend_host__startswith="http"):
        host = route.backend_host
        for scheme in ("https://", "http://"):
            if host.startswith(scheme):
                route.backend_host = host[len(scheme):]
                route.save(update_fields=["backend_host"])
                break


class Migration(migrations.Migration):

    dependencies = [
        ("ingress", "0002_route_dns_ok"),
    ]

    operations = [
        migrations.RunPython(strip_scheme, migrations.RunPython.noop),
    ]
