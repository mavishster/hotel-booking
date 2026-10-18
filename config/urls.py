
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from hotel.views import (
    StaffLoginView,
    StaffLogoutView,
    booking_create,
    booking_list,
    dashboard,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", StaffLoginView.as_view(), name="login"),
    path("logout/", StaffLogoutView.as_view(), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("bookings/", booking_list, name="booking_list"),
    path(
        "",
        RedirectView.as_view(
            pattern_name="dashboard",
            permanent=False,
        ),
        name="home",
    ),
    path("bookings/new/", booking_create, name="booking_create"),
]
