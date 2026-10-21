
from django import forms

from .models import Bed, Booking, Room
from .services import validate_booking
from django.utils.translation import gettext_lazy as _


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
    dietary_requirements = forms.MultipleChoiceField(
        choices=[
            ("vegetarian", _("Vegetarian")),
            ("vegan", _("Vegan")),
            ("halal", _("Halal")),
            ("gluten_free", _("Gluten-free")),
            ("lactose_free", _("Lactose-free")),
            ("no_pork", _("No pork")),
            ("other", _("Other")),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Dietary requirements"),
    )
    booking_source = forms.ChoiceField(
        choices=Booking.BookingSource.choices,
        required=False,
        label="Источник бронирования",
    )
    cancellation_reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

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
            "status",
            "cancellation_reason",
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
        self.fields["room"].empty_label = _("Select an option")
        self.fields["booking_mode"].choices = [
            ("", _("Select an option")),
            *Booking.BookingMode.choices,
        ]

        self.fields["room"].queryset = Room.objects.filter(
            is_active=True,
        ).select_related("room_type")

        self.fields["beds"].queryset = Bed.objects.filter(
            is_active=True,
            room__is_active=True,
        ).select_related("room").order_by("room__number", "number")

    def clean(self):
        cleaned_data = super().clean()
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
                        if field in self.fields:
                            for message in errors:
                                self.add_error(field, message)
                        else:
                            for message in errors:
                                self.add_error(None, message)
                else:
                    self.add_error(None, error)

        return cleaned_data

    def clean_breakfast_count(self):
        return self.cleaned_data.get("breakfast_count") or 0

    def clean_lunch_count(self):
        return self.cleaned_data.get("lunch_count") or 0

    def clean_dinner_count(self):
        return self.cleaned_data.get("dinner_count") or 0
