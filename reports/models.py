from django.db import models
from django.conf import settings


class CollectionRoute(models.Model):
    route_name = models.CharField(max_length=200)
    bins = models.ManyToManyField('bins.SmartBin', related_name='routes')
    total_distance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_time = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.route_name


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('bin_full', 'Bin Full'),
        ('payment_received', 'Payment Received'),
        ('route_assigned', 'Route Assigned'),
        ('system', 'System'),
    ]
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.title


class CollectionSchedule(models.Model):
    TIME_SLOT_CHOICES = [
        ('morning', 'Morning (6AM - 10AM)'),
        ('midday', 'Midday (10AM - 2PM)'),
        ('afternoon', 'Afternoon (2PM - 6PM)'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    collector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collection_schedules')
    household = models.ForeignKey('accounts.Household', on_delete=models.CASCADE, related_name='collection_schedules')
    bin = models.ForeignKey('bins.SmartBin', on_delete=models.SET_NULL, null=True, blank=True, related_name='collection_schedules')
    scheduled_date = models.DateField()
    time_slot = models.CharField(max_length=20, choices=TIME_SLOT_CHOICES, default='morning')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Schedule: {self.collector.username} -> {self.household.name} on {self.scheduled_date}"