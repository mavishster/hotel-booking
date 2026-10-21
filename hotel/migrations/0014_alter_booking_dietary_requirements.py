
from django.db import migrations, models


def prepare_dietary_requirements(apps, schema_editor):
    Booking = apps.get_model("hotel", "Booking")
    database = schema_editor.connection.alias

    for booking in Booking.objects.using(database).all().iterator():
        value = booking.dietary_requirements

        if not value or not value.strip():
            booking.dietary_requirements = "[]"
        else:
            import json
            booking.dietary_requirements = json.dumps([value])

        booking.save(
            using=database,
            update_fields=["dietary_requirements"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("hotel", "0013_remove_roomtype_allergies_and_more"),
    ]

    operations = [
        migrations.RunPython(
            prepare_dietary_requirements,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="booking",
            name="dietary_requirements",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
