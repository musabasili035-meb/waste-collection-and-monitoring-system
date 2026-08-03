from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Household

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'user_type', 'is_staff']
    list_filter = ['user_type', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('user_type', 'phone', 'address', 'latitude', 'longitude', 'profile_image')}),
    )

@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'address', 'contact_phone', 'created_at']
    search_fields = ['name', 'address']
    list_filter = ['created_at']