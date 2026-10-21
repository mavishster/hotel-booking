
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from hotel.views import (
    StaffLoginView,
    StaffLogoutView,
    booking_create,
    booking_change_status,
    booking_detail,
    booking_edit,
    booking_list,
    dashboard,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
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
    path("bookings/<int:booking_id>/", booking_detail, name="booking_detail"),
    path("bookings/<int:booking_id>/edit/", booking_edit, name="booking_edit"),
    path("bookings/<int:booking_id>/status/", booking_change_status, name="booking_change_status"),
]
