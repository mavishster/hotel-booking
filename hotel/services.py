
from .models import Booking


def find_booking_conflicts(
    *,
    room,
    booking_mode,
    beds,
    check_in,
    check_out,
    exclude_booking_id=None,
):
    """
    Возвращает активные брони, конфликтующие с новой бронью.

    День выезда не считается занятой ночью.
    """
    overlapping = Booking.objects.filter(
        room=room,
        status=Booking.Status.ACTIVE,
        check_in__lt=check_out,
        check_out__gt=check_in,
    )

    if exclude_booking_id is not None:
        overlapping = overlapping.exclude(pk=exclude_booking_id)

    if booking_mode == Booking.BookingMode.ROOM:
        return overlapping

    if booking_mode == Booking.BookingMode.BED:
        room_bookings = overlapping.filter(
            booking_mode=Booking.BookingMode.ROOM,
        )

        bed_bookings = overlapping.filter(
            booking_mode=Booking.BookingMode.BED,
            beds__in=beds,
        )

        return (room_bookings | bed_bookings).distinct()

    return Booking.objects.none()
