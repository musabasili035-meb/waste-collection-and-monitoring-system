from django.db import models
from django.conf import settings


class SmartBin(models.Model):
    bin_id = models.CharField(max_length=100, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, default=0)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, default=0)
    location_name = models.CharField(max_length=255, blank=True)
    household = models.ForeignKey('accounts.Household', on_delete=models.SET_NULL, null=True, blank=True, related_name='bins')
    assigned_collector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_bins')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    STATUS_CHOICES = [
        ('empty', 'Empty'),
        ('moderate', 'Moderate'),
        ('full', 'Full'),
    ]
    
    @property
    def status(self):
        latest_data = self.iot_data.first()
        if not latest_data:
            return 'empty'
        if latest_data.garbage_level > 80:
            return 'full'
        elif latest_data.garbage_level > 30:
            return 'moderate'
        return 'empty'
    
    @property
    def current_garbage_level(self):
        latest = self.iot_data.first()
        return float(latest.garbage_level) if latest else 0
    
    @property
    def current_recyclable_level(self):
        latest = self.iot_data.first()
        return float(latest.recyclable_level) if latest else 0
    
    @property
    def current_recyclable_weight(self):
        latest = self.iot_data.first()
        return float(latest.recyclable_weight) if latest else 0
    
    @property
    def last_updated(self):
        latest = self.iot_data.first()
        return latest.timestamp if latest else None
    
    def __str__(self):
        return f"Bin {self.bin_id}"


class IoTData(models.Model):
    bin = models.ForeignKey(SmartBin, on_delete=models.CASCADE, related_name='iot_data')
    garbage_level = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    recyclable_level = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    recyclable_weight = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Data for Bin {self.bin.bin_id} at {self.timestamp}"