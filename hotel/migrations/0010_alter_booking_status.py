from django.db import migrations, models


def convert_booking_statuses(apps, schema_editor):
    Booking = apps.get_model("hotel", "Booking")

    Booking.objects.filter(status="ACTIVE").update(
        status="CONFIRMED"
    )


class Migration(migrations.Migration):

    dependencies = [
        (
            "hotel",
            "0009_booking_booking_reference_booking_booking_source_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            convert_booking_statuses,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="booking",
            name="status",
            field=models.CharField(
                choices=[
                    ("TENTATIVE", "Предварительное"),
                    ("CONFIRMED", "Подтверждено"),
                    ("CHECKED_IN", "Гость заселился"),
                    ("CHECKED_OUT", "Гость выехал"),
                    ("CANCELLED", "Отменено"),
                    ("NO_SHOW", "Неявка"),
                ],
                default="CONFIRMED",
                max_length=12,
            ),
        ),
    ]