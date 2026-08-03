from django.contrib import admin
from .models import CollectionRoute, Notification

@admin.register(CollectionRoute)
class CollectionRouteAdmin(admin.ModelAdmin):
    list_display = ['route_name', 'total_distance', 'estimated_time', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message']
