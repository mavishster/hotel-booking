
import calendar
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.utils import timezone

from .models import Booking, Room
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
