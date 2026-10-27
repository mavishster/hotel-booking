
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import BookingAdminForm
from .forms import BookingForm
from .models import Bed
from .services import find_booking_conflicts

from decimal import Decimal
from .services import calculate_children_surcharge

from .models import Booking, Bed, Payment, RatePlan, RateRule, Room, RoomType
from .services import (
    calculate_booking_total,
    calculate_children_surcharge,
    find_booking_conflicts,
    get_room_rate_for_date,
)

class BookingModelTests(TestCase):
    def setUp(self):
        self.room_type = RoomType.objects.create(
            name="Glamping",
            capacity=6,
        )

        self.room = Room.objects.create(
            room_type=self.room_type,
            number="TEST-101",
        )

    def test_checkout_must_be_after_checkin(self):
        booking = Booking(
            room=self.room,
            booking_mode=Booking.BookingMode.BED,
            check_in=date(2026, 10, 17),
            check_out=date(2026, 10, 17),
            adults_count=1,
        )

        with self.assertRaises(ValidationError):
            booking.full_clean()


    def test_valid_date_range_passes_validation(self):
        booking = Booking(
            room=self.room,
            booking_mode=Booking.BookingMode.BED,
            check_in=date(2026, 10, 17),
            check_out=date(2026, 10, 19),
            adults_count=1,
        )

        booking.full_clean()

class BookingAdminFormTests(TestCase):
    def setUp(self):
        room_type = RoomType.objects.create(
            name="Glamping",
            capacity=6,
        )

        self.room = Room.objects.create(
            room_type=room_type,
            number="TEST-101",
        )

        self.bed = Bed.objects.create(
            room=self.room,
            number="1",
        )

        existing_booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.BED,
            check_in=date(2026, 10, 17),
            check_out=date(2026, 10, 19),
            adults_count=1,
        )
        existing_booking.beds.add(self.bed)

    def test_cannot_book_same_bed_for_overlapping_dates(self):
        form = BookingAdminForm(
            data={
                "room": self.room.pk,
                "booking_mode": Booking.BookingMode.BED,
                "beds": [self.bed.pk],
                "check_in": "2026-10-18",
                "check_out": "2026-10-20",
                "adults_count": 1,
                "status": Booking.Status.CONFIRMED,
                "guest_name": "",
                "guest_phone": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("beds", form.errors)

    def test_can_book_bed_when_previous_booking_checks_out_that_day(self):
        form = BookingAdminForm(
            data={
                "room": self.room.pk,
                "booking_mode": Booking.BookingMode.BED,
                "beds": [self.bed.pk],
                "check_in": "2026-10-19",
                "check_out": "2026-10-21",
                "adults_count": 1,
                "status": Booking.Status.CONFIRMED,
                "guest_name": "",
                "guest_phone": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_cannot_book_whole_room_when_bed_is_already_booked(self):
        form = BookingAdminForm(
            data={
                "room": self.room.pk,
                "booking_mode": Booking.BookingMode.ROOM,
                "beds": [],
                "check_in": "2026-10-18",
                "check_out": "2026-10-20",
                "adults_count": 2,
                "status": Booking.Status.CONFIRMED,
                "guest_name": "",
                "guest_phone": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("room", form.errors)

    def test_cannot_book_bed_when_whole_room_is_already_booked(self):
        whole_room_booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.ROOM,
            check_in=date(2026, 10, 17),
            check_out=date(2026, 10, 19),
            adults_count=2,
        )

        form = BookingAdminForm(
            data={
                "room": self.room.pk,
                "booking_mode": Booking.BookingMode.BED,
                "beds": [self.bed.pk],
                "check_in": "2026-10-18",
                "check_out": "2026-10-20",
                "adults_count": 1,
                "status": Booking.Status.CONFIRMED,
                "guest_name": "",
                "guest_phone": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("beds", form.errors)

    def test_cannot_book_multiple_beds_if_one_is_occupied(self):
        second_bed = Bed.objects.create(
            room=self.room,
            number="2",
        )

        existing_booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.BED,
            check_in=date(2026, 10, 17),
            check_out=date(2026, 10, 19),
            adults_count=1,
        )
        existing_booking.beds.add(self.bed)

        form = BookingAdminForm(
            data={
                "room": self.room.pk,
                "booking_mode": Booking.BookingMode.BED,
                "beds": [self.bed.pk, second_bed.pk],
                "check_in": "2026-10-18",
                "check_out": "2026-10-20",
                "adults_count": 2,
                "status": Booking.Status.CONFIRMED,
                "guest_name": "",
                "guest_phone": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("beds", form.errors)

    def test_editing_booking_does_not_conflict_with_itself(self):
        Booking.objects.all().delete()
        existing_booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.BED,
            check_in=date(2026, 10, 17),
            check_out=date(2026, 10, 19),
            adults_count=1,
        )
        existing_booking.beds.add(self.bed)

        form = BookingAdminForm(
            data={
                "room": self.room.pk,
                "booking_mode": Booking.BookingMode.BED,
                "beds": [self.bed.pk],
                "check_in": "2026-10-17",
                "check_out": "2026-10-19",
                "adults_count": 1,
                "status": Booking.Status.CONFIRMED,
                "guest_name": "",
                "guest_phone": "",
            },
            instance=existing_booking,
        )

        self.assertTrue(form.is_valid(), form.errors)

class ChildrenSurchargeTests(TestCase):
    def test_first_child_under_seven_is_free(self):
        self.assertEqual(
            calculate_children_surcharge(2000, [4]),
            Decimal("0.00"),
        )

    def test_additional_children_under_seven_pay_half(self):
        self.assertEqual(
            calculate_children_surcharge(2000, [3, 6]),
            Decimal("1000.00"),
        )

    def test_children_aged_seven_to_twelve_pay_half(self):
        self.assertEqual(
            calculate_children_surcharge(2000, [7, 12]),
            Decimal("2000.00"),
        )

    def test_children_over_twelve_pay_full_rate(self):
        self.assertEqual(
            calculate_children_surcharge(2000, [13]),
            Decimal("2000.00"),
        )

    def test_mixed_children_ages(self):
        self.assertEqual(
            calculate_children_surcharge(2000, [4, 6, 9, 13]),
            Decimal("4000.00"),
        )


class BookingPriceTests(TestCase):
    def setUp(self):
        self.room_type = RoomType.objects.create(
            name="Glamping",
            capacity=6,
        )
        self.room = Room.objects.create(
            room_type=self.room_type,
            number="PRICE-101",
        )
        self.plan = RatePlan.objects.create(
            name="Базовый тариф",
            booking_mode=RatePlan.BookingMode.ROOM,
            room_type=self.room_type,
        )
        RateRule.objects.create(
            rate_plan=self.plan,
            name="Базовая цена",
            is_base=True,
            price=Decimal("2000.00"),
        )

    def test_returns_base_rate(self):
        self.assertEqual(
            get_room_rate_for_date(
                self.room,
                Booking.BookingMode.ROOM,
                date(2026, 10, 20),
            ),
            Decimal("2000.00"),
        )

    def test_seasonal_rule_overrides_base_rate(self):
        RateRule.objects.create(
            rate_plan=self.plan,
            name="Специальная цена",
            price=Decimal("3000.00"),
            start_date=date(2026, 10, 20),
            end_date=date(2026, 10, 25),
            priority=10,
        )

        self.assertEqual(
            get_room_rate_for_date(
                self.room,
                Booking.BookingMode.ROOM,
                date(2026, 10, 22),
            ),
            Decimal("3000.00"),
        )

    def test_calculates_two_nights_with_child_surcharge(self):
        booking = Booking(
            room=self.room,
            booking_mode=Booking.BookingMode.ROOM,
            check_in=date(2026, 10, 20),
            check_out=date(2026, 10, 22),
            adults_count=2,
            children_count=1,
            children_ages=[10],
        )

        self.assertEqual(
            calculate_booking_total(booking),
            Decimal("6000.00"),
        )


class OwnerReportViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="hotel-owner",
            password="test-password",
        )
        self.room_type = RoomType.objects.create(name="Glamping", capacity=4)
        self.room = Room.objects.create(
            room_type=self.room_type,
            number="REPORT-101",
        )
        today = timezone.localdate()
        self.booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.ROOM,
            check_in=today,
            check_out=today + timedelta(days=1),
            adults_count=2,
            total_price=Decimal("1200.00"),
        )
        Payment.objects.create(
            booking=self.booking,
            transaction_type=Payment.TransactionType.PAYMENT,
            amount=Decimal("500.00"),
        )
        self.client.force_login(self.user)

    def test_reports_summarize_bookings_payments_and_occupancy(self):
        response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["booking_count"], 1)
        self.assertEqual(response.context["booked_revenue"], Decimal("1200.00"))
        self.assertEqual(response.context["net_collected"], Decimal("500.00"))
        self.assertEqual(response.context["occupied_unit_nights"], 1)
        self.assertEqual(response.context["total_unit_nights"], response.context["report_days"])

    def test_reports_filter_dates_and_subtract_refunds(self):
        today = timezone.localdate()
        Payment.objects.create(
            booking=self.booking,
            transaction_type=Payment.TransactionType.REFUND,
            amount=Decimal("100.00"),
        )
        response = self.client.get(
            reverse("reports"),
            {"start_date": today.isoformat(), "end_date": today.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["report_days"], 1)
        self.assertEqual(response.context["booking_count"], 1)
        self.assertEqual(response.context["net_collected"], Decimal("400.00"))
        self.assertEqual(response.context["occupied_unit_nights"], 1)
        self.assertEqual(response.context["total_unit_nights"], 1)

    def test_bed_booking_occupancy_counts_only_the_booked_bed(self):
        first_bed = Bed.objects.create(room=self.room, number=1)
        Bed.objects.create(room=self.room, number=2)
        self.booking.booking_mode = Booking.BookingMode.BED
        self.booking.save(update_fields=["booking_mode"])
        self.booking.beds.add(first_bed)
        today = timezone.localdate()

        response = self.client.get(
            reverse("reports"),
            {"start_date": today.isoformat(), "end_date": today.isoformat()},
        )

        self.assertEqual(response.context["occupancy_percent"], 50.0)
        self.assertEqual(response.context["occupied_unit_nights"], 1)
        self.assertEqual(response.context["total_unit_nights"], 2)

    def test_reports_reject_invalid_date_ranges(self):
        response = self.client.get(
            reverse("reports"),
            {"start_date": "2026-03-10", "end_date": "2026-03-01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["messages"])


class BookingListStatusTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="booking-list-owner",
            password="test-password",
        )
        self.client.force_login(user)
        room_type = RoomType.objects.create(name="Glamping", capacity=4)
        self.room = Room.objects.create(
            room_type=room_type,
            number="LIST-101",
        )

    def test_booking_list_shows_each_actual_status(self):
        today = timezone.localdate()
        status_labels = dict(Booking.Status.choices)
        for index, status in enumerate(Booking.Status.values):
            Booking.objects.create(
                room=self.room,
                booking_mode=Booking.BookingMode.ROOM,
                check_in=today + timedelta(days=index),
                check_out=today + timedelta(days=index + 1),
                adults_count=1,
                status=status,
            )

        response = self.client.get(reverse("booking_list"))

        self.assertEqual(response.status_code, 200)
        for status in Booking.Status.values:
            self.assertContains(response, str(status_labels[status]))
        self.assertNotContains(response, ">Active</span>")

    def test_booking_list_links_to_booking_edit_page(self):
        today = timezone.localdate()
        booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.ROOM,
            check_in=today,
            check_out=today + timedelta(days=1),
            adults_count=1,
        )

        response = self.client.get(reverse("booking_list"))

        self.assertContains(
            response,
            f'href="{reverse("booking_edit", args=[booking.pk])}"',
        )
        self.assertContains(response, "Редактировать бронирование")

    def test_edit_form_shows_existing_booking_dates(self):
        check_in = date(2026, 11, 12)
        check_out = date(2026, 11, 16)
        booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.ROOM,
            check_in=check_in,
            check_out=check_out,
            adults_count=1,
        )

        response = self.client.get(reverse("booking_edit", args=[booking.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'value="{check_in.isoformat()}"',
        )
        self.assertContains(
            response,
            f'value="{check_out.isoformat()}"',
        )

    def test_disallowed_status_transition_shows_one_validation_error(self):
        today = timezone.localdate()
        booking = Booking.objects.create(
            room=self.room,
            booking_mode=Booking.BookingMode.ROOM,
            check_in=today + timedelta(days=1),
            check_out=today + timedelta(days=2),
            adults_count=1,
            status=Booking.Status.CONFIRMED,
        )
        form = BookingForm(
            data={
                "guest_name": "",
                "guest_phone": "",
                "guest_email": "",
                "room": self.room.pk,
                "booking_mode": Booking.BookingMode.ROOM,
                "check_in": (today + timedelta(days=1)).isoformat(),
                "check_out": (today + timedelta(days=2)).isoformat(),
                "adults_count": "1",
                "children_count": "0",
                "children_ages": "[]",
                "booking_source": Booking.BookingSource.OTHER,
                "status": Booking.Status.CHECKED_OUT,
                "cancellation_reason": "",
                "special_requests": "",
                "breakfast_count": "0",
                "lunch_count": "0",
                "dinner_count": "0",
                "dietary_requirements": [],
                "allergies": "",
                "meal_notes": "",
            },
            instance=booking,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            len(form.errors.as_data()["status"]),
            1,
        )
