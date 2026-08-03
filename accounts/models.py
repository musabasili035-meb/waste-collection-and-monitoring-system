from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = [
        ('admin', 'Admin (System Controller)'),
        ('collector', 'Collector (Waste Collector)'),
        ('household', 'Household (Resident)'),
    ]
    
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='household')
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def is_admin(self):
        return self.user_type == 'admin'
    
    def is_collector(self):
        return self.user_type == 'collector'
    
    def is_household(self):
        return self.user_type == 'household'
    
    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"


class Household(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='households')
    name = models.CharField(max_length=200)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    passport_photo = models.ImageField(upload_to='household_photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name