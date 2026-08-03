from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta, date
import uuid
import random
from .models import Payment, Receipt
from bins.models import SmartBin, IoTData
from accounts.models import Household
from django.db.models import Sum, Count, Q


def get_fill_frequency(bin_obj, days=30):
    cutoff = timezone.now() - timedelta(days=days)
    count = IoTData.objects.filter(
        bin=bin_obj,
        garbage_level__gt=80,
        timestamp__gte=cutoff,
    ).count()
    return count


def get_frequency_multiplier(fill_count):
    tiers = getattr(settings, 'FILL_FREQUENCY_TIERS', [(3, 1.0), (7, 1.5), (999, 2.0)])
    for max_count, multiplier in tiers:
        if fill_count <= max_count:
            return multiplier
    return 1.0


def get_monthly_discount_rate(months):
    rates = getattr(settings, 'MONTHLY_FEE_DISCOUNT_RATES', [(1, 1.0), (3, 0.95), (6, 0.90), (12, 0.85)])
    for m, rate in rates:
        if months == m:
            return rate
    return 1.0


class PaymentCreateView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        data = request.data
        user = request.user
        
        if user.user_type not in ['household', 'admin']:
            return Response({'error': 'Unauthorized to make payments'}, status=status.HTTP_403_FORBIDDEN)
        
        bin_id = data.get('bin_id')
        
        if not bin_id:
            return Response({'error': 'Bin ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            bin_obj = SmartBin.objects.get(bin_id=bin_id)
        except SmartBin.DoesNotExist:
            return Response({'error': f'Bin "{bin_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        household = bin_obj.household
        if not household:
            try:
                household = Household.objects.filter(user=user).first()
            except Exception:
                pass
        if not household:
            return Response({'error': 'No household found for this bin. Please contact admin.'}, status=status.HTTP_400_BAD_REQUEST)

        months = int(data.get('months', 1))
        if months not in [m for m, _ in getattr(settings, 'MONTHLY_FEE_DISCOUNT_RATES', [(1, 1.0)])]:
            months = 1

        fill_count = get_fill_frequency(bin_obj)
        freq_mult = get_frequency_multiplier(fill_count) if months > 1 else 1.0
        monthly_mult = get_monthly_discount_rate(months)

        recyclable_weight = float(data.get('recyclable_weight', 0))
        discount = recyclable_weight * getattr(settings, 'RECYCLABLE_RATE_PER_KG', 500)
        base_monthly_fee = getattr(settings, 'DEFAULT_WASTE_FEE', 2000)
        adjusted_monthly = base_monthly_fee * freq_mult * monthly_mult
        total = max((adjusted_monthly * months) - discount, 0)

        today = date.today()
        period_start = today
        period_end = date(today.year + ((today.month + months - 1) // 12),
                         ((today.month + months - 1) % 12) or 12, 1) - timedelta(days=1)

        transaction_id = f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"

        payment = Payment.objects.create(
            user=user,
            household=household,
            bin=bin_obj,
            amount=round(adjusted_monthly * months, 2),
            recyclable_discount=discount,
            total_amount=round(total, 2),
            payment_status='completed',
            transaction_id=transaction_id,
            period_start=period_start,
            period_end=period_end,
            months_covered=months,
            fill_frequency_score=fill_count,
            frequency_multiplier=round(freq_mult, 2),
        )
        
        receipt_number = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        Receipt.objects.create(
            receipt_number=receipt_number,
            payment=payment,
            user_name=household.name,
            user_address=household.address,
            bin_id=bin_obj.bin_id,
            amount_paid=round(total, 2),
            discount_applied=discount,
        )
        
        return Response({
            'success': True,
            'transaction_id': transaction_id,
            'receipt_number': receipt_number,
            'amount_paid': round(total, 2),
            'discount_applied': discount,
            'fill_frequency_score': fill_count,
            'frequency_multiplier': round(freq_mult, 2),
            'months_covered': months,
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat(),
            'monthly_rate': round(adjusted_monthly, 2),
        }, status=status.HTTP_201_CREATED)


class ReceiptListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if request.user.user_type == 'collector':
            receipts = Receipt.objects.all()
        else:
            receipts = Receipt.objects.filter(payment__user=request.user)
        data = []
        for receipt in receipts:
            data.append({
                'id': receipt.id,
                'receipt_number': receipt.receipt_number,
                'user_name': receipt.user_name,
                'user_address': receipt.user_address,
                'bin_id': receipt.bin_id,
                'amount_paid': float(receipt.amount_paid),
                'discount_applied': float(receipt.discount_applied),
                'recyclable_weight': 0,
                'payment_method': receipt.payment.payment_method if hasattr(receipt.payment, 'payment_method') else 'mobile_money',
                'date_issued': receipt.date_issued.isoformat(),
            })
        return Response(data)


class PaymentHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        payments = Payment.objects.filter(user=request.user)
        data = []
        for payment in payments:
            data.append({
                'transaction_id': payment.transaction_id,
                'household': payment.household.name,
                'bin_id': payment.bin.bin_id,
                'amount': float(payment.amount),
                'discount': float(payment.recyclable_discount),
                'total': float(payment.total_amount),
                'status': payment.payment_status,
                'date': payment.payment_date.isoformat(),
                'period_start': payment.period_start.isoformat() if payment.period_start else None,
                'period_end': payment.period_end.isoformat() if payment.period_end else None,
                'months_covered': payment.months_covered,
                'fill_frequency_score': payment.fill_frequency_score,
                'frequency_multiplier': float(payment.frequency_multiplier) if payment.frequency_multiplier else 1.0,
            })
        return Response(data)


class AllPaymentsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        if user.user_type not in ['admin', 'collector']:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        payments = Payment.objects.all()
        data = []
        for payment in payments:
            data.append({
                'household': payment.household.name,
                'bin_id': payment.bin.bin_id,
                'transaction_id': payment.transaction_id,
                'amount': float(payment.total_amount),
                'status': payment.payment_status,
                'date': payment.payment_date.isoformat(),
                'period_start': payment.period_start.isoformat() if payment.period_start else None,
                'period_end': payment.period_end.isoformat() if payment.period_end else None,
                'months_covered': payment.months_covered,
                'fill_frequency_score': payment.fill_frequency_score,
                'frequency_multiplier': float(payment.frequency_multiplier),
            })
        return Response(data)


@api_view(['GET'])
def calculate_fee(request):
    bin_id = request.GET.get('bin_id')
    recyclable_weight = float(request.GET.get('recyclable_weight', 0))
    months = int(request.GET.get('months', 1))
    if months not in [m for m, _ in getattr(settings, 'MONTHLY_FEE_DISCOUNT_RATES', [(1, 1.0)])]:
        months = 1
    
    discount = recyclable_weight * getattr(settings, 'RECYCLABLE_RATE_PER_KG', 500)
    base_monthly_fee = getattr(settings, 'DEFAULT_WASTE_FEE', 2000)
    
    fill_count = 0
    freq_mult = 1.0
    if bin_id:
        try:
            bin_obj = SmartBin.objects.get(bin_id=bin_id)
            fill_count = get_fill_frequency(bin_obj)
            freq_mult = get_frequency_multiplier(fill_count) if months > 1 else 1.0
        except SmartBin.DoesNotExist:
            pass
    
    monthly_mult = get_monthly_discount_rate(months)
    adjusted_monthly = base_monthly_fee * freq_mult * monthly_mult
    total = max((adjusted_monthly * months) - discount, 0)
    
    return Response({
        'base_monthly_fee': base_monthly_fee,
        'fill_frequency_score': fill_count,
        'frequency_multiplier': freq_mult,
        'months': months,
        'monthly_discount_rate': monthly_mult,
        'adjusted_monthly_rate': round(adjusted_monthly, 2),
        'recyclable_weight': recyclable_weight,
        'discount': round(discount, 2),
        'total': round(total, 2),
    })