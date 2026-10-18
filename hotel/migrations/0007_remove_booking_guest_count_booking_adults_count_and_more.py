
from django.db import migrations, models


def copy_guest_count(apps, schema_editor):
    Booking = apps.get_model("hotel", "Booking")

    for booking in Booking.objects.all().iterator():
        booking.adults_count = booking.guest_count
        booking.free_children_count = 0
        booking.save(
            update_fields=["adults_count", "free_children_count"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("hotel", "0006_booking_guest_name_booking_guest_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="adults_count",
            field=models.PositiveSmallIntegerField(
                default=1,
                verbose_name="Количество взрослых",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="free_children_count",
            field=models.PositiveSmallIntegerField(
                default=0,
                verbose_name="Бесплатные дети до 10 лет",
            ),
        ),
        migrations.RunPython(
            copy_guest_count,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="booking",
            name="guest_count",
        ),
    ]
