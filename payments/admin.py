from django.contrib import admin
from .models import Payment, Receipt

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'user', 'household', 'amount', 'payment_status', 'payment_date']
    list_filter = ['payment_status', 'payment_date']
    search_fields = ['transaction_id', 'user__username']

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'payment', 'user_name', 'amount_paid', 'date_issued']
    search_fields = ['receipt_number', 'user_name']
