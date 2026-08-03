from django.db import models
from django.conf import settings


class Payment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    household = models.ForeignKey('accounts.Household', on_delete=models.CASCADE, related_name='payments')
    bin = models.ForeignKey('bins.SmartBin', on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    recyclable_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_status = models.CharField(max_length=20, default='pending')
    payment_method = models.CharField(max_length=50, default='mobile_money')
    transaction_id = models.CharField(max_length=100, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    months_covered = models.PositiveIntegerField(default=1)
    fill_frequency_score = models.PositiveIntegerField(default=0)
    frequency_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)
    
    def __str__(self):
        return f"Payment {self.transaction_id} - {self.amount} TZS"


class Receipt(models.Model):
    receipt_number = models.CharField(max_length=100, unique=True)
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='receipt')
    user_name = models.CharField(max_length=200)
    user_address = models.TextField()
    bin_id = models.CharField(max_length=100)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    discount_applied = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_issued = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Receipt {self.receipt_number}"