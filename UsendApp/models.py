from django.db import models
from django.contrib.auth.models import User
import math


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Returns distance in kilometres between two GPS points.
    Uses the Haversine formula — no PostGIS needed.
    """
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class Profile(models.Model):
    USER_TYPE_CHOICES = [
        ('client', 'Client'),
        ('runner', 'Runner'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='client')
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    # Runner's live location — updated whenever they open the dashboard
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    # Rating (avg of all reviews received)
    rating = models.FloatField(default=0.0)
    rating_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f'{self.user.username} ({self.user_type})'

    def update_rating(self):
        reviews = self.user.reviews_received.all()
        if reviews.exists():
            self.rating = reviews.aggregate(models.Avg('score'))['score__avg']
            self.rating_count = reviews.count()
            self.save(update_fields=['rating', 'rating_count'])

    @property
    def stars(self):
        """Returns rating rounded to nearest 0.5 for display."""
        return round(self.rating * 2) / 2


class Task(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Paid', 'Paid'),
        ('Cancelled', 'Cancelled'),
    ]

    CATEGORY_CHOICES = [
        ('delivery', 'Delivery'),
        ('shopping', 'Shopping'),
        ('pickup', 'Pickup'),
        ('document', 'Document'),
        ('other', 'Other'),
    ]

    client = models.ForeignKey(User, related_name='tasks', on_delete=models.CASCADE)
    runner = models.ForeignKey(
        User, related_name='assigned_tasks',
        null=True, blank=True, on_delete=models.SET_NULL
    )

    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    phone_number = models.CharField(max_length=15, null=True, blank=True)

    # Human-readable addresses
    location_from = models.CharField(max_length=255)
    location_to = models.CharField(max_length=255)

    # GPS coordinates of the pickup point — used for 3km radius filter
    pickup_latitude = models.FloatField(null=True, blank=True)
    pickup_longitude = models.FloatField(null=True, blank=True)

    # Pricing
    client_budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    proposed_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Deadline
    deadline = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def distance_to_runner(self, runner_profile):
        """Returns km distance from this task's pickup to the runner's location."""
        if None in (self.pickup_latitude, self.pickup_longitude,
                    runner_profile.latitude, runner_profile.longitude):
            return None
        return haversine_distance(
            self.pickup_latitude, self.pickup_longitude,
            runner_profile.latitude, runner_profile.longitude,
        )

    @classmethod
    def nearby_pending(cls, runner_profile, radius_km=3):
        """
        Returns Pending tasks within radius_km of the runner.
        Falls back to ALL pending tasks if the runner has no location yet.
        """
        pending = cls.objects.filter(status='Pending').select_related('client')

        if runner_profile.latitude is None or runner_profile.longitude is None:
            for task in pending:
                task.distance = None
            return list(pending)

        nearby = []
        for task in pending:
            dist = task.distance_to_runner(runner_profile)
            if dist is None or dist <= radius_km:
                task._distance = round(dist, 2) if dist is not None else None
                nearby.append(task)

        nearby.sort(key=lambda t: t._distance if t._distance is not None else 999)
        return nearby

    @property
    def is_reviewed(self):
        return hasattr(self, 'review')


class PriceCounter(models.Model):
    """
    Tracks price negotiation between runner and client.
    Multiple counters are allowed per task (back-and-forth).
    """
    task = models.ForeignKey(Task, related_name='counters', on_delete=models.CASCADE)
    proposed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_accepted = models.BooleanField(null=True)  # None=pending, True=accepted, False=declined

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.proposed_by.username} proposed KSh {self.amount} for "{self.task.title}"'


class Notification(models.Model):
    """
    In-app notifications. Created by signals/views, read in the nav/dashboard.
    """
    TYPES = [
        ('price_proposed', 'Runner proposed a price'),
        ('price_countered', 'Counter-offer received'),
        ('task_accepted', 'Task accepted'),
        ('task_declined', 'Task declined'),
        ('task_completed', 'Task completed'),
        ('payment_received', 'Payment received'),
        ('review_received', 'Review received'),
    ]
    recipient = models.ForeignKey(User, related_name='notifications', on_delete=models.CASCADE)
    notif_type = models.CharField(max_length=30, choices=TYPES)
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'→ {self.recipient.username}: {self.message}'


class Review(models.Model):
    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name='review')
    reviewer = models.ForeignKey(User, related_name='reviews_given', on_delete=models.CASCADE)
    reviewee = models.ForeignKey(User, related_name='reviews_received', on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField()   # 1–5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.reviewee.profile.update_rating()

    def __str__(self):
        return f'{self.reviewer.username} → {self.reviewee.username}: {self.score}/5'