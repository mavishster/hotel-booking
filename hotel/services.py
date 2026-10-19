from datetime import timedelta
from decimal import Decimal

from django.db import models

from .models import Booking, RatePlan, RateRule


def get_room_rate_for_date(room, booking_mode, date):
    """Возвращает цену за ночь с учетом тарифов и приоритетов."""
    rate_plans = list(
        RatePlan.objects.filter(
            is_active=True,
            booking_mode=booking_mode,
        ).filter(
            models.Q(room=room)
            | models.Q(room_type=room.room_type)
        )
    )

    if not rate_plans:
        raise ValueError(
            f"Не найден активный тариф для комнаты {room.number}"
        )

    plan_ids = [plan.pk for plan in rate_plans]

    applicable_rules = list(
        RateRule.objects.filter(
            rate_plan_id__in=plan_ids,
            is_active=True,
            is_base=False,
        ).filter(
            models.Q(start_date__isnull=True)
            | models.Q(start_date__lte=date),
            models.Q(end_date__isnull=True)
            | models.Q(end_date__gte=date),
        ).select_related("rate_plan")
    )

    applicable_rules = [
        rule for rule in applicable_rules
        if not rule.weekdays or date.weekday() in rule.weekdays
    ]

    applicable_rules.sort(
        key=lambda rule: (
            -rule.priority,
            0 if rule.rate_plan.room_id == room.pk else 1,
            rule.pk,
        )
    )

    if applicable_rules:
        return applicable_rules[0].price

    base_rules = list(
        RateRule.objects.filter(
            rate_plan_id__in=plan_ids,
            is_active=True,
            is_base=True,
        ).select_related("rate_plan")
    )

    base_rules.sort(
        key=lambda rule: (
            0 if rule.rate_plan.room_id == room.pk else 1,
            rule.pk,
        )
    )

    if base_rules:
        return base_rules[0].price

    raise ValueError(
        f"Не найден базовый тариф для комнаты {room.number} "
        f"на {date:%d.%m.%Y}"
    )

def calculate_children_surcharge(room_rate, children_ages):
    """Рассчитывает доплату за детей за одну ночь."""
    room_rate = Decimal(str(room_rate))
    free_child_used = False
    surcharge = Decimal("0.00")

    for age in children_ages:
        if 0 <= age <= 6 and not free_child_used:
            free_child_used = True
        elif age <= 12:
            surcharge += room_rate * Decimal("0.50")
        else:
            surcharge += room_rate

    return surcharge.quantize(Decimal("0.01"))

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
        status__in=[
            Booking.Status.TENTATIVE,
            Booking.Status.CONFIRMED,
            Booking.Status.CHECKED_IN,
        ],
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


def calculate_booking_total(booking, beds_count=1):
    """Рассчитывает полную стоимость бронирования."""
    total = Decimal("0.00")
    current_date = booking.check_in

    while current_date < booking.check_out:
        nightly_rate = get_room_rate_for_date(
            booking.room,
            booking.booking_mode,
            current_date,
        )

        if booking.booking_mode == Booking.BookingMode.ROOM:
            nightly_total = nightly_rate + calculate_children_surcharge(
                nightly_rate,
                booking.children_ages or [],
            )
        else:
            nightly_total = nightly_rate * beds_count

        total += nightly_total
        current_date += timedelta(days=1)

    return total.quantize(Decimal("0.01"))
