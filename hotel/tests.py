
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from .admin import BookingAdminForm
from .models import Bed
from .services import find_booking_conflicts

from decimal import Decimal
from .services import calculate_children_surcharge

from .models import Booking, Bed, RatePlan, RateRule, Room, RoomType
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
