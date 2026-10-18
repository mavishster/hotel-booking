
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.utils import timezone

from .models import Booking, Room
from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import BookingForm

class StaffLoginView(LoginView):
    template_name = "hotel/login.html"
    redirect_authenticated_user = True


class StaffLogoutView(LogoutView):
    next_page = reverse_lazy("login")


@login_required
def dashboard(request):
    today = timezone.localdate()

    context = {
        "active_bookings": Booking.objects.filter(
            status=Booking.Status.ACTIVE,
        ).count(),
        "active_rooms": Room.objects.filter(is_active=True).count(),
        "arrivals_today": Booking.objects.filter(
            status=Booking.Status.ACTIVE,
            check_in=today,
        ).count(),
        "departures_today": Booking.objects.filter(
            status=Booking.Status.ACTIVE,
            check_out=today,
        ).count(),
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
            booking = form.save()
            messages.success(
                request,
                f"Booking for {booking.guest_name or 'guest'} created successfully.",
            )
            return redirect("booking_list")
    else:
        form = BookingForm()

    return render(
        request,
        "hotel/booking_form.html",
        {"form": form},
    )
