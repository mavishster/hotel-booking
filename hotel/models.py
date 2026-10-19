
from django.db import models
from django.conf import settings

class RoomType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    capacity = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)
    breakfast = models.BooleanField(default=False)
    lunch = models.BooleanField(default=False)
    dinner = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Room(models.Model):
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.PROTECT,
        related_name="rooms",
    )
    number = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Комната {self.number}"


class Bed(models.Model):
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="beds",
    )
    number = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "number"],
                name="unique_bed_number_per_room",
            ),
        ]

    def __str__(self):
        return f"Комната {self.room.number}, место {self.number}"


class RatePlan(models.Model):
    class BookingMode(models.TextChoices):
        BED = "BED", "Отдельное место"
        ROOM = "ROOM", "Комната целиком"

    name = models.CharField(max_length=100)
    booking_mode = models.CharField(
        max_length=10,
        choices=BookingMode.choices,
    )

    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.PROTECT,
        related_name="rate_plans",
        null=True,
        blank=True,
    )

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="rate_plans",
        null=True,
        blank=True,
    )

    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)


    def clean(self):
        from django.core.exceptions import ValidationError

        if bool(self.room_type_id) == bool(self.room_id):
            raise ValidationError(
                "Укажите либо тип комнаты, либо конкретную комнату."
            )


    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(room_type__isnull=False)
                        & models.Q(room__isnull=True)
                    )
                    |
                    (
                        models.Q(room_type__isnull=True)
                        & models.Q(room__isnull=False)
                    )
                ),
                name="rate_plan_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=models.Q(booking_mode__in=["BED", "ROOM"]),
                name="rate_plan_valid_booking_mode",
            ),
        ]


    def __str__(self):
        return f"{self.name} ({self.get_booking_mode_display()})"


class RateRule(models.Model):
    rate_plan = models.ForeignKey(
        RatePlan,
        on_delete=models.CASCADE,
        related_name="price_rules",
    )
    name = models.CharField(max_length=100)


    is_base = models.BooleanField(
        default=False,
        help_text="Базовая цена тарифа, действующая по умолчанию",
    )

    price = models.DecimalField(max_digits=10, decimal_places=2)

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    weekdays = models.JSONField(
        default=list,
        blank=True,
        help_text="Дни недели: 0 — понедельник, 6 — воскресенье",
    )

    priority = models.PositiveIntegerField(
        default=0,
        help_text="Чем больше число, тем выше приоритет правила",
    )

    is_active = models.BooleanField(default=True)


    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}


        if self.is_base:
            if self.priority != 0:
                errors["priority"] = (
                    "Базовое правило должно иметь приоритет 0."
                )

            if self.start_date or self.end_date:
                errors["start_date"] = (
                    "Базовое правило не должно иметь ограничений по датам."
                )

            if self.weekdays:
                errors["weekdays"] = (
                    "Базовое правило не должно иметь ограничений по дням недели."
                )


        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                errors["end_date"] = (
                    "Дата окончания не может быть раньше даты начала."
                )

        if not isinstance(self.weekdays, list):
            errors["weekdays"] = (
                "Дни недели должны быть списком чисел от 0 до 6."
            )
        elif any(
            type(day) is not int or day < 0 or day > 6
            for day in self.weekdays
        ):
            errors["weekdays"] = (
                "Дни недели должны быть числами от 0 до 6."
            )

        if errors:
            raise ValidationError(errors)


    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="rate_rule_price_non_negative",
            ),
            models.UniqueConstraint(
                fields=["rate_plan"],
                condition=models.Q(is_base=True),
                name="unique_base_rule_per_rate_plan",
            ),
        ]



    def __str__(self):
        return f"{self.name}: {self.price}"


class Booking(models.Model):
    class BookingMode(models.TextChoices):
        BED = "BED", "Отдельные кровати"
        ROOM = "ROOM", "Glamping целиком"

    class Status(models.TextChoices):
        TENTATIVE = "TENTATIVE", "Предварительное"
        CONFIRMED = "CONFIRMED", "Подтверждено"
        CHECKED_IN = "CHECKED_IN", "Гость заселился"
        CHECKED_OUT = "CHECKED_OUT", "Гость выехал"
        CANCELLED = "CANCELLED", "Отменено"
        NO_SHOW = "NO_SHOW", "Неявка"

    class BookingSource(models.TextChoices):
        PHONE = "PHONE", "Телефон"
        WALK_IN = "WALK_IN", "Лично"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        WEBSITE = "WEBSITE", "Сайт"
        BOOKING_COM = "BOOKING_COM", "Booking.com"
        OTHER = "OTHER", "Другое"

    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        related_name="bookings",
    )

    booking_mode = models.CharField(
        max_length=10,
        choices=BookingMode.choices,
    )

    beds = models.ManyToManyField(
        Bed,
        blank=True,
        related_name="bookings",
    )

    check_in = models.DateField()
    check_out = models.DateField()

    adults_count = models.PositiveSmallIntegerField(
        verbose_name="Количество взрослых",
    )

    # Новые поля о детях.
    children_count = models.PositiveSmallIntegerField(default=0)
    children_ages = models.JSONField(default=list, blank=True)

    guest_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )
    guest_phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )
    guest_email = models.EmailField(blank=True)

    booking_reference = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
    )

    booking_source = models.CharField(
        max_length=12,
        choices=BookingSource.choices,
        default=BookingSource.OTHER,
    )

    special_requests = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    breakfast_count = models.PositiveSmallIntegerField(default=0)
    lunch_count = models.PositiveSmallIntegerField(default=0)
    dinner_count = models.PositiveSmallIntegerField(default=0)

    dietary_requirements = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    meal_notes = models.TextField(blank=True)

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    price_overridden = models.BooleanField(default=False)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bookings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}

        if self.check_in and self.check_out:
            if self.check_out <= self.check_in:
                errors["check_out"] = (
                    "Дата выезда должна быть позже даты заезда."
                )

        if self.adults_count < 1:
            errors["adults_count"] = (
                "Количество взрослых должно быть не меньше одного."
            )

        if self.room_id and self.booking_mode == self.BookingMode.ROOM:
            total_guests = self.adults_count + self.children_count

            if total_guests > self.room.room_type.capacity:
                errors["adults_count"] = (
                    "Общее количество гостей превышает вместимость помещения."
                )

        if not isinstance(self.children_ages, list):
            errors["children_ages"] = (
                "Возраст детей должен быть списком."
            )
        elif any(
            type(age) is not int or age < 0 or age > 17
            for age in self.children_ages
        ):
            errors["children_ages"] = (
                "Возраст каждого ребёнка должен быть от 0 до 17 лет."
            )
        elif len(self.children_ages) != self.children_count:
            errors["children_ages"] = (
                "Количество возрастов должно совпадать "
                "с количеством детей."
            )
     
        if errors:
            raise ValidationError(errors)

    @property
    def guest_count(self):
        return self.adults_count + self.children_count

    def __str__(self):
        return (
            f"{self.room.number}: "
            f"{self.check_in} — {self.check_out}"
        )

class Payment(models.Model):
    class TransactionType(models.TextChoices):
        PAYMENT = "PAYMENT", "Payment"
        REFUND = "REFUND", "Refund"

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        CARD = "CARD", "Card"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        ONLINE = "ONLINE", "Online"
        OTHER = "OTHER", "Other"

    booking = models.ForeignKey(
        Booking,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
        default=TransactionType.PAYMENT,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.CASH,
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.get_transaction_type_display()} "
            f"{self.amount} — {self.booking}"
        )