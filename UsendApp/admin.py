from django.contrib import admin
from .models import Profile, Task, Review, PriceCounter, Notification


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_type', 'phone_number', 'rating', 'rating_count')
    list_filter = ('user_type',)
    search_fields = ('user__username', 'user__email', 'phone_number')
    readonly_fields = ('rating', 'rating_count', 'latitude', 'longitude', 'location_updated_at')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'runner', 'category', 'status', 'proposed_price', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'client__username', 'runner__username', 'location_from', 'location_to')
    readonly_fields = ('created_at', 'updated_at', 'pickup_latitude', 'pickup_longitude')
    date_hierarchy = 'created_at'


@admin.register(PriceCounter)
class PriceCounterAdmin(admin.ModelAdmin):
    list_display = ('task', 'proposed_by', 'amount', 'is_accepted', 'created_at')
    list_filter = ('is_accepted',)
    search_fields = ('task__title', 'proposed_by__username')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('task', 'reviewer', 'reviewee', 'score', 'created_at')
    list_filter = ('score',)
    search_fields = ('reviewer__username', 'reviewee__username', 'comment')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notif_type', 'message', 'is_read', 'created_at')
    list_filter = ('notif_type', 'is_read')
    search_fields = ('recipient__username', 'message')
    actions = ['mark_read']

    @admin.action(description='Mark selected notifications as read')
    def mark_read(self, request, queryset):
        queryset.update(is_read=True)