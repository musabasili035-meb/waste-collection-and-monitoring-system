from django.contrib import admin
from .models import SmartBin, IoTData

@admin.register(SmartBin)
class SmartBinAdmin(admin.ModelAdmin):
    list_display = ['bin_id', 'latitude', 'longitude', 'household', 'assigned_collector', 'is_active', 'created_at']
    search_fields = ['bin_id', 'location_name']
    list_filter = ['is_active', 'created_at']

@admin.register(IoTData)
class IoTDataAdmin(admin.ModelAdmin):
    list_display = ['bin', 'garbage_level', 'recyclable_level', 'recyclable_weight', 'timestamp']
    list_filter = ['timestamp', 'bin']
    date_hierarchy = 'timestamp'