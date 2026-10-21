
from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, reverse
from .models import Bed, Booking, RatePlan, RateRule, Room, RoomType
from .services import save_booking_safely, validate_booking


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

        beds = cleaned_data.get("beds")
        if all(cleaned_data.get(field) is not None for field in (
            "room", "booking_mode", "check_in", "check_out", "adults_count", "children_count"
        )):
            candidate = self.instance
            for field in (
                "room", "booking_mode", "check_in", "check_out", "adults_count",
                "children_count", "children_ages", "status",
            ):
                if field in cleaned_data:
                    setattr(candidate, field, cleaned_data[field])
            try:
                candidate.full_clean(exclude=["beds"])
                validate_booking(candidate, beds)
            except forms.ValidationError as error:
                if hasattr(error, "message_dict"):
                    for field, errors in error.message_dict.items():
                        for message in errors:
                            self.add_error(field if field in self.fields else None, message)
                else:
                    self.add_error(None, error)

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

    def save_model(self, request, obj, form, change):
        obj.created_by = obj.created_by or request.user
        beds = form.cleaned_data.get("beds", [])
        save_booking_safely(obj, beds)

    def save_related(self, request, form, formsets, change):
        # BookingForm's M2M value is committed under the same room lock in save_model.
        super().save_related(request, form, formsets, change)
