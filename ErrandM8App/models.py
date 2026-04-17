from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import math, random, string


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def _otp():
    return ''.join(random.choices(string.digits, k=6))


class Profile(models.Model):
    USER_TYPE_CHOICES = [
        ('client', 'Client'),
        ('concierge', 'Concierge'),   # DB value stays 'runner' for migration compatibility
    ]

    user              = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type         = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='client')
    phone_number      = models.CharField(max_length=15, null=True, blank=True)
    bio               = models.TextField(blank=True)
    avatar            = models.ImageField(upload_to='avatars/', null=True, blank=True)

    phone_verified      = models.BooleanField(default=False)
    otp_code            = models.CharField(max_length=6, blank=True)
    otp_created_at      = models.DateTimeField(null=True, blank=True)
    two_fa_enabled      = models.BooleanField(default=False)

    latitude            = models.FloatField(null=True, blank=True)
    longitude           = models.FloatField(null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    rating       = models.FloatField(default=0.0)
    rating_count = models.PositiveIntegerField(default=0)

    is_online       = models.BooleanField(default=False)
    total_earned    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    jobs_completed  = models.PositiveIntegerField(default=0)

    def __str__(self):
        label = 'Concierge' if self.user_type == 'concierge' else 'Client'
        return f'{self.user.username} ({label})'

    def generate_otp(self):
        self.otp_code = _otp()
        self.otp_created_at = timezone.now()
        self.save(update_fields=['otp_code', 'otp_created_at'])
        return self.otp_code

    def otp_valid(self, code):
        if not self.otp_code or not self.otp_created_at:
            return False
        expired = (timezone.now() - self.otp_created_at).seconds > 600
        return (not expired) and (self.otp_code == code)

    def update_rating(self):
        from django.db.models import Avg
        reviews = self.user.reviews_received.all()
        if reviews.exists():
            self.rating = reviews.aggregate(Avg('score'))['score__avg']
            self.rating_count = reviews.count()
            self.save(update_fields=['rating', 'rating_count'])

    @property
    def stars(self):
        return round(self.rating * 2) / 2

    @property
    def display_role(self):
        return 'Concierge' if self.user_type == 'concierge' else 'Client'


class Task(models.Model):
    STATUS_CHOICES = [
        ('Pending',     'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed',   'Completed'),
        ('Paid',        'Paid'),
        ('Cancelled',   'Cancelled'),
    ]
    CATEGORY_CHOICES = [
        ('delivery',    'Parcel Delivery'),
        ('shopping',    'Grocery Shopping'),
        ('babysitting', 'Babysitting'),
        ('pickup',      'Pickup'),
        ('document',    'Document'),
        ('cleaning',    'Cleaning'),
        ('cooking',     'Cooking'),
        ('laundry',     'Laundry'),
        ('errands',     'General Errands'),
        ('other',       'Other'),
    ]

    client   = models.ForeignKey(User, related_name='tasks', on_delete=models.CASCADE)
    runner   = models.ForeignKey(User, related_name='assigned_tasks', null=True, blank=True, on_delete=models.SET_NULL)

    title        = models.CharField(max_length=255)
    description  = models.TextField()
    category     = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    phone_number = models.CharField(max_length=15, null=True, blank=True)

    location_from    = models.CharField(max_length=255)
    location_to      = models.CharField(max_length=255)
    pickup_latitude  = models.FloatField(null=True, blank=True)
    pickup_longitude = models.FloatField(null=True, blank=True)

    client_budget  = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    proposed_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    deadline       = models.DateTimeField(null=True, blank=True)

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def distance_to_concierge(self, concierge_profile):
        if None in (self.pickup_latitude, self.pickup_longitude,
                    concierge_profile.latitude, concierge_profile.longitude):
            return None
        return haversine_distance(
            self.pickup_latitude, self.pickup_longitude,
            concierge_profile.latitude, concierge_profile.longitude,
        )

    @classmethod
    def nearby_pending(cls, concierge_profile, radius_km=3):
        pending = cls.objects.filter(status='Pending').select_related('client')
        if concierge_profile.latitude is None:
            for t in pending:
                t._distance = None
            return list(pending)
        nearby = []
        for task in pending:
            dist = task.distance_to_concierge(concierge_profile)
            if dist is None or dist <= radius_km:
                task._distance = round(dist, 2) if dist is not None else None
                nearby.append(task)
        nearby.sort(key=lambda t: t._distance if t._distance is not None else 999)
        return nearby

    @property
    def is_reviewed(self):
        return hasattr(self, 'review')


class PriceCounter(models.Model):
    task        = models.ForeignKey(Task, related_name='counters', on_delete=models.CASCADE)
    proposed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    note        = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    is_accepted = models.BooleanField(null=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.proposed_by.username} → KSh {self.amount} for "{self.task.title}"'


class ChatMessage(models.Model):
    task      = models.ForeignKey(Task, related_name='messages', on_delete=models.CASCADE)
    sender    = models.ForeignKey(User, on_delete=models.CASCADE)
    body      = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read   = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender.username}: {self.body[:40]}'


class Notification(models.Model):
    TYPES = [
        ('price_proposed',   'Concierge proposed a price'),
        ('price_countered',  'Counter-offer received'),
        ('task_accepted',    'Errand accepted'),
        ('task_declined',    'Errand declined'),
        ('task_completed',   'Errand completed'),
        ('payment_received', 'Payment received'),
        ('review_received',  'Review received'),
        ('chat_message',     'New message'),
        ('otp',              'OTP sent'),
    ]
    recipient  = models.ForeignKey(User, related_name='notifications', on_delete=models.CASCADE)
    notif_type = models.CharField(max_length=30, choices=TYPES)
    task       = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE)
    message    = models.CharField(max_length=255)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'→ {self.recipient.username}: {self.message}'


class Review(models.Model):
    task       = models.OneToOneField(Task, on_delete=models.CASCADE, related_name='review')
    reviewer   = models.ForeignKey(User, related_name='reviews_given',    on_delete=models.CASCADE)
    reviewee   = models.ForeignKey(User, related_name='reviews_received', on_delete=models.CASCADE)
    score      = models.PositiveSmallIntegerField()
    comment    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.reviewee.profile.update_rating()

    def __str__(self):
        return f'{self.reviewer.username} → {self.reviewee.username}: {self.score}/5'
