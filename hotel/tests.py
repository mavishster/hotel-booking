
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Booking, Room, RoomType
from .admin import BookingAdminForm
from .models import Bed
from .services import find_booking_conflicts

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
                "free_children_count": 0,
                "status": Booking.Status.ACTIVE,
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
                "free_children_count": 0,
                "status": Booking.Status.ACTIVE,
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
                "free_children_count": 0,
                "status": Booking.Status.ACTIVE,
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
                "free_children_count": 0,
                "status": Booking.Status.ACTIVE,
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
                "free_children_count": 0,
                "status": Booking.Status.ACTIVE,
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
                "free_children_count": 0,
                "status": Booking.Status.ACTIVE,
                "guest_name": "",
                "guest_phone": "",
            },
            instance=existing_booking,
        )

        self.assertTrue(form.is_valid(), form.errors)
