
from django import forms

from .models import Bed, Booking, Room
from .services import find_booking_conflicts


class BookingForm(forms.ModelForm):
    beds = forms.ModelMultipleChoiceField(
        queryset=Bed.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Beds",
    )
    children_count = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label="Количество детей",
    )
    breakfast_count = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Breakfasts needed (included)",
    )
    lunch_count = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Lunches needed",
    )
    dinner_count = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Dinners needed",
    )

    class Meta:
        model = Booking
        fields = [
            "guest_name",
            "guest_phone",
            "guest_email",
            "room",
            "booking_mode",
            "beds",
            "check_in",
            "check_out",
            "adults_count",
            "children_count",
            "children_ages",
            "booking_source",
            "special_requests",
            "breakfast_count",
            "lunch_count",
            "dinner_count",
            "dietary_requirements",
            "allergies",
            "meal_notes",
        ]
        widgets = {
            "check_in": forms.DateInput(attrs={"type": "date"}),
            "check_out": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        
        super().__init__(*args, **kwargs)

        self.fields["room"].queryset = Room.objects.filter(
            is_active=True,
        ).select_related("room_type")

        self.fields["beds"].queryset = Bed.objects.filter(
            is_active=True,
            room__is_active=True,
        ).select_related("room").order_by("room__number", "number")

    def clean(self):
        cleaned_data = super().clean()

        room = cleaned_data.get("room")
        booking_mode = cleaned_data.get("booking_mode")
        beds = cleaned_data.get("beds")
        check_in = cleaned_data.get("check_in")
        check_out = cleaned_data.get("check_out")

        if room and booking_mode == Booking.BookingMode.BED:
            if not beds:
                self.add_error(
                    "beds",
                    "Select at least one bed for a bed booking.",
                )
            elif any(bed.room_id != room.id for bed in beds):
                self.add_error(
                    "beds",
                    "All selected beds must belong to the selected room.",
                )

        if booking_mode == Booking.BookingMode.ROOM and beds:
            self.add_error(
                "beds",
                "Do not select individual beds when booking the whole room.",
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
                        "The room or one of its beds is already booked "
                        "for these dates.",
                    )
                else:
                    self.add_error(
                        "beds",
                        "One or more selected beds are already booked "
                        "for these dates.",
                    )

        return cleaned_data

    def clean_breakfast_count(self):
        return self.cleaned_data.get("breakfast_count") or 0

    def clean_lunch_count(self):
        return self.cleaned_data.get("lunch_count") or 0

    def clean_dinner_count(self):
        return self.cleaned_data.get("dinner_count") or 0