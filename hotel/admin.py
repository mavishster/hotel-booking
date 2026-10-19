
from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, reverse
from .models import Bed, Booking, RatePlan, RateRule, Room, RoomType
from .services import find_booking_conflicts


admin.site.register(RoomType)
admin.site.register(Room)
admin.site.register(Bed)
admin.site.register(RatePlan)
admin.site.register(RateRule)


class BookingAdminForm(forms.ModelForm):
    children_count = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Количество детей",
    )

    breakfast_count = forms.IntegerField(
        min_value=0, required=False, initial=0
    )
    lunch_count = forms.IntegerField(
        min_value=0, required=False, initial=0
    )
    dinner_count = forms.IntegerField(
        min_value=0, required=False, initial=0
    )

    booking_source = forms.ChoiceField(
        choices=Booking.BookingSource.choices,
        required=False,
        initial=Booking.BookingSource.OTHER,
        label="Источник бронирования",
    )
    class Meta:
        model = Booking
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["room"].widget.attrs["data-bed-options-url"] = reverse(
            "admin:hotel_booking_bed_options"
        )

        room_id = None

        if self.is_bound:
            room_id = self.data.get("room")
        elif self.instance and self.instance.pk:
            room_id = self.instance.room_id

        if room_id:
            self.fields["beds"].queryset = Bed.objects.filter(
                room_id=room_id,
                is_active=True,
            )
        else:
            self.fields["beds"].queryset = Bed.objects.none()


    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get("children_count") is None:
            cleaned_data["children_count"] = 0

        if not cleaned_data.get("booking_source"):
            cleaned_data["booking_source"] = Booking.BookingSource.OTHER

        room = cleaned_data.get("room")
        booking_mode = cleaned_data.get("booking_mode")
        beds = cleaned_data.get("beds")
        check_in = cleaned_data.get("check_in")
        check_out = cleaned_data.get("check_out")

        if room and booking_mode == Booking.BookingMode.BED:
            if not beds:
                self.add_error(
                    "beds",
                    "Для бронирования отдельных кроватей выберите хотя бы одну.",
                )
            elif any(bed.room_id != room.id for bed in beds):
                self.add_error(
                    "beds",
                    "Все выбранные кровати должны относиться к выбранной комнате.",
                )

        if booking_mode == Booking.BookingMode.ROOM and beds:
            self.add_error(
                "beds",
                "При бронировании комнаты целиком отдельные кровати выбирать не нужно.",
            )

        if (
            room
            and check_in
            and check_out
            and check_out > check_in
            and booking_mode in (
                Booking.BookingMode.BED,
                Booking.BookingMode.ROOM,
            )
        ):
            conflicts = find_booking_conflicts(
                room=room,
                booking_mode=booking_mode,
                beds=beds if beds else [],
                check_in=check_in,
                check_out=check_out,
                exclude_booking_id=self.instance.pk,
            )

            if conflicts.exists():
                if booking_mode == Booking.BookingMode.ROOM:
                    self.add_error(
                        "room",
                        "Помещение или одна из его кроватей уже забронированы на эти даты.",
                    )
                else:
                    self.add_error(
                        "beds",
                        "Одна или несколько выбранных кроватей уже заняты на эти даты.",
                    )

        return cleaned_data


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    form = BookingAdminForm

    list_display = (
        "guest_name",
        "guest_phone",
        "room",
        "booking_mode",
        "check_in",
        "check_out",
        "status",
    )

    list_filter = (
        "status",
        "booking_mode",
        "room",
    )

    search_fields = (
        "guest_name",
        "guest_phone",
    )

    date_hierarchy = "check_in"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "bed-options/",
                self.admin_site.admin_view(self.bed_options_view),
                name="hotel_booking_bed_options",
            ),
        ]
        return custom_urls + urls

    def bed_options_view(self, request):
        room_id = request.GET.get("room_id")

        beds = Bed.objects.none()

        if room_id and room_id.isdigit():
            beds = Bed.objects.filter(
                room_id=int(room_id),
                is_active=True,
            ).order_by("number")

        return JsonResponse(
            [
                {"id": bed.id, "label": str(bed)}
                for bed in beds
            ],
            safe=False,
        )

    class Media:
        js = ("hotel/admin/booking_form.js",)
