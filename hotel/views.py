
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count, Q, Sum
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Bed, Booking, Payment, Room
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.core.exceptions import ValidationError

from .forms import BookingForm

from .services import calculate_booking_total, save_booking_safely

class StaffLoginView(LoginView):
    template_name = "hotel/login.html"
    redirect_authenticated_user = True


class StaffLogoutView(LogoutView):
    next_page = reverse_lazy("login")


@login_required
def dashboard(request):
    today = timezone.localdate()

    try:
        month = int(request.GET.get("month", today.month))
        year = int(request.GET.get("year", today.year))
        first_day = date(year, month, 1)
    except (TypeError, ValueError):
        first_day = today.replace(day=1)
        year, month = first_day.year, first_day.month

    month_grid_start = first_day - timedelta(days=first_day.weekday())
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    month_grid_end = last_day + timedelta(days=(6 - last_day.weekday()))
    days = [
        month_grid_start + timedelta(days=offset)
        for offset in range((month_grid_end - month_grid_start).days + 1)
    ]
    rooms = list(Room.objects.filter(is_active=True).select_related("room_type").order_by("number"))
    bookings = (
        Booking.objects.filter(
            room__in=rooms,
            check_in__lte=month_grid_end,
            check_out__gt=month_grid_start,
        )
        .exclude(status__in=[Booking.Status.CANCELLED, Booking.Status.NO_SHOW])
        .select_related("room")
        .prefetch_related("beds")
        .order_by("check_in")
    )
    bookings_by_room = {room.id: [] for room in rooms}
    for booking in bookings:
        bookings_by_room[booking.room_id].append(booking)

    calendar_rows = []
    for room in rooms:
        cells = []
        for day in days:
            day_bookings = [
                booking for booking in bookings_by_room[room.id]
                if booking.check_in <= day < booking.check_out
            ]
            cells.append({"day": day, "bookings": day_bookings})
        calendar_rows.append({"room": room, "cells": cells})

    previous_month = first_day - timedelta(days=1)
    next_month = last_day + timedelta(days=1)

    context = {
        "active_bookings": Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
        ).count(),
        "active_rooms": Room.objects.filter(is_active=True).count(),
        "arrivals_today": Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            check_in=today,
        ).count(),
        "departures_today": Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            check_out=today,
        ).count(),
        "calendar_days": days,
        "calendar_rows": calendar_rows,
        "calendar_month": first_day,
        "calendar_previous": previous_month,
        "calendar_next": next_month,
        "calendar_today": today,
    }

    return render(request, "hotel/dashboard.html", context)
@login_required
def booking_list(request):
    bookings = (
        Booking.objects
        .select_related("room")
        .prefetch_related("beds")
        .order_by("check_in", "room__number")
    )

    return render(
        request,
        "hotel/booking_list.html",
        {"bookings": bookings},
    )


@login_required
def reports(request):
    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = date(
        today.year,
        today.month,
        calendar.monthrange(today.year, today.month)[1],
    )
    start_date = default_start
    end_date = default_end

    requested_start = request.GET.get("start_date")
    requested_end = request.GET.get("end_date")
    if requested_start or requested_end:
        try:
            start_date = date.fromisoformat(requested_start)
            end_date = date.fromisoformat(requested_end)
        except (TypeError, ValueError):
            messages.error(request, _("Enter valid start and end dates."))
            start_date, end_date = default_start, default_end
        else:
            if end_date < start_date:
                messages.error(request, _("The end date must be on or after the start date."))
                start_date, end_date = default_start, default_end
            elif (end_date - start_date).days >= 90:
                messages.error(request, _("Choose a date range of 90 days or less."))
                start_date, end_date = default_start, default_end

    days = [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]
    report_bookings = Booking.objects.filter(check_in__range=(start_date, end_date))
    revenue_bookings = report_bookings.filter(
        status__in=[
            Booking.Status.CONFIRMED,
            Booking.Status.CHECKED_IN,
            Booking.Status.CHECKED_OUT,
        ],
    )
    booked_revenue = (
        revenue_bookings.aggregate(total=Sum("total_price"))["total"]
        or Decimal("0.00")
    )
    payment_rows = (
        Payment.objects.filter(created_at__date__range=(start_date, end_date))
        .values("created_at__date")
        .annotate(
            collected=Sum("amount", filter=Q(transaction_type=Payment.TransactionType.PAYMENT)),
            refunded=Sum("amount", filter=Q(transaction_type=Payment.TransactionType.REFUND)),
        )
    )
    daily_payments = {
        row["created_at__date"]: (row["collected"] or Decimal("0.00"))
        - (row["refunded"] or Decimal("0.00"))
        for row in payment_rows
    }
    net_collected = sum(daily_payments.values(), Decimal("0.00"))
    max_daily_amount = max(
        (abs(amount) for amount in daily_payments.values()),
        default=Decimal("0.00"),
    )
    daily_chart = [
        {
            "day": day,
            "amount": daily_payments.get(day, Decimal("0.00")),
            "height": (
                max(4, round(abs(daily_payments.get(day, Decimal("0.00"))) / max_daily_amount * 100))
                if max_daily_amount
                else 0
            ),
        }
        for day in days
    ]

    active_rooms = list(
        Room.objects.filter(is_active=True)
        .select_related("room_type")
        .order_by("number")
    )
    active_beds_by_room = {room.pk: set() for room in active_rooms}
    for bed in Bed.objects.filter(
        room_id__in=active_beds_by_room,
        is_active=True,
    ).values("id", "room_id"):
        active_beds_by_room[bed["room_id"]].add(bed["id"])
    inventory_units_by_room = {
        room_id: len(bed_ids) or 1
        for room_id, bed_ids in active_beds_by_room.items()
    }
    occupied_units_by_room = {room.pk: {} for room in active_rooms}
    occupancy_bookings = (
        Booking.objects.filter(
            room__in=active_rooms,
            check_in__lt=end_date + timedelta(days=1),
            check_out__gt=start_date,
            status__in=[
                Booking.Status.CONFIRMED,
                Booking.Status.CHECKED_IN,
                Booking.Status.CHECKED_OUT,
            ],
        )
        .select_related("room")
        .prefetch_related("beds")
    )
    for booking in occupancy_bookings:
        room_id = booking.room_id
        if booking.booking_mode == Booking.BookingMode.ROOM:
            occupied_units = active_beds_by_room[room_id] or {None}
        else:
            occupied_units = {
                bed.pk for bed in booking.beds.all()
                if bed.is_active and bed.room_id == room_id
            }
        first_night = max(start_date, booking.check_in)
        last_night = min(end_date + timedelta(days=1), booking.check_out)
        for offset in range((last_night - first_night).days):
            night = first_night + timedelta(days=offset)
            occupied_units_by_room[room_id].setdefault(night, set()).update(
                occupied_units
            )

    total_unit_nights = sum(inventory_units_by_room.values()) * len(days)
    occupied_unit_nights = sum(
        len(units) for occupied_by_night in occupied_units_by_room.values()
        for units in occupied_by_night.values()
    )
    occupancy_percent = (
        round(occupied_unit_nights / total_unit_nights * 100, 1)
        if total_unit_nights
        else 0
    )
    room_chart = []
    for room in active_rooms:
        unit_nights = sum(
            len(units)
            for units in occupied_units_by_room[room.pk].values()
        )
        total_room_unit_nights = inventory_units_by_room[room.pk] * len(days)
        room_chart.append({
            "room": room,
            "unit_nights": unit_nights,
            "total_unit_nights": total_room_unit_nights,
            "percent": round(unit_nights / total_room_unit_nights * 100, 1),
        })
    room_chart.sort(key=lambda item: (-item["unit_nights"], item["room"].number))
    room_chart = room_chart[:8]

    status_counts = report_bookings.values("status").annotate(total=Count("id")).order_by()
    status_labels = dict(Booking.Status.choices)
    booking_statuses = [
        {"label": status_labels.get(row["status"], row["status"]), "count": row["total"]}
        for row in status_counts
    ]
    source_counts = (
        report_bookings.values("booking_source")
        .annotate(total=Count("id"))
        .order_by("-total", "booking_source")
    )
    source_labels = dict(Booking.BookingSource.choices)
    booking_sources = [
        {
            "label": source_labels.get(row["booking_source"], row["booking_source"]),
            "count": row["total"],
        }
        for row in source_counts
    ]
    max_mix_count = max(
        [item["count"] for item in booking_statuses + booking_sources],
        default=0,
    )
    for item in booking_statuses + booking_sources:
        item["width"] = round(item["count"] / max_mix_count * 100) if max_mix_count else 0

    return render(request, "hotel/reports.html", {
        "start_date": start_date,
        "end_date": end_date,
        "report_days": len(days),
        "booking_count": report_bookings.count(),
        "booked_revenue": booked_revenue,
        "net_collected": net_collected,
        "occupancy_percent": occupancy_percent,
        "occupied_unit_nights": occupied_unit_nights,
        "total_unit_nights": total_unit_nights,
        "daily_chart": daily_chart,
        "room_chart": room_chart,
        "booking_statuses": booking_statuses,
        "booking_sources": booking_sources,
    })



@login_required
def booking_create(request):
    if request.method == "POST":
        form = BookingForm(request.POST)

        if form.is_valid():
            booking = form.save(commit=False)

            try:
                booking.total_price = calculate_booking_total(
                    booking,
                    beds_count=form.cleaned_data["beds"].count(),
                )
            except ValueError as error:
                form.add_error(None, str(error))
            else:
                booking.created_by = request.user
                try:
                    save_booking_safely(booking, form.cleaned_data["beds"])
                except ValidationError as error:
                    for field, errors in getattr(error, "message_dict", {}).items():
                        for message in errors:
                            form.add_error(field if field in form.fields else None, message)
                else:

                    messages.success(
                        request,
                        f"Бронирование для {booking.guest_name or 'гостя'} создано. "
                        f"Стоимость: {booking.total_price} KGS.",
                    )
                    return redirect("booking_list")
       

    else:
        initial = {}
        for field in ("room", "check_in", "check_out"):
            if request.GET.get(field):
                initial[field] = request.GET[field]
        form = BookingForm(initial=initial)

    return render(
        request,
        "hotel/booking_form.html",
        {"form": form},
    )


@login_required
def booking_detail(request, booking_id):
    booking = (
        Booking.objects.select_related("room")
        .prefetch_related("beds")
        .get(pk=booking_id)
    )
    return render(request, "hotel/booking_detail.html", {
        "booking": booking,
        "allowed_statuses": booking.STATUS_TRANSITIONS.get(booking.status, set()),
        "status_choices": Booking.Status.choices,
    })


@login_required
def booking_change_status(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    if request.method == "POST":
        new_status = request.POST.get("status")
        reason = request.POST.get("cancellation_reason", "")
        try:
            from django.db import transaction
            with transaction.atomic():
                locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
                booking.refresh_from_db()
                if booking.status != locked_booking.status:
                    booking = locked_booking
                booking.transition_to(new_status, reason=reason)
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
        else:
            messages.success(request, "Booking status updated.")
    else:
        return redirect("booking_detail", booking_id=booking.pk)
    return redirect("booking_detail", booking_id=booking.pk)


@login_required
def booking_edit(request, booking_id):
    booking = get_object_or_404(Booking.objects.prefetch_related("beds"), pk=booking_id)
    if request.method == "POST":
        form = BookingForm(request.POST, instance=booking)
        if form.is_valid():
            updated_booking = form.save(commit=False)
            try:
                updated_booking.total_price = calculate_booking_total(
                    updated_booking,
                    beds_count=form.cleaned_data["beds"].count(),
                )
            except ValueError as error:
                form.add_error(None, str(error))
            else:
                try:
                    save_booking_safely(updated_booking, form.cleaned_data["beds"])
                except ValidationError as error:
                    for field, errors in getattr(error, "message_dict", {}).items():
                        for message in errors:
                            form.add_error(field if field in form.fields else None, message)
                else:
                    messages.success(request, "Бронирование обновлено.")
                    return redirect("booking_detail", booking_id=booking.pk)
    else:
        form = BookingForm(instance=booking)
    return render(
        request,
        "hotel/booking_form.html",
        {"form": form, "booking": booking},
    )
