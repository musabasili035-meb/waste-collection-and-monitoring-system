from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q, Count, Sum, Max
from django.utils import timezone
from datetime import timedelta
from .models import CustomUser, Household
from bins.models import SmartBin, IoTData
from payments.models import Payment, Receipt
from reports.models import Notification, CollectionSchedule
from reports.views import clarke_wright_savings, calculate_total_distance, haversine_distance, _get_collector_depot


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    user = request.user
    
    total_households = Household.objects.count()
    total_bins = SmartBin.objects.count()
    active_bins = SmartBin.objects.filter(is_active=True).count()
    
    full_bins_count = 0
    total_waste = 0
    total_recyclable = 0
    total_weight = 0
    for bin_obj in SmartBin.objects.filter(is_active=True):
        latest = bin_obj.iot_data.first()
        if latest:
            if latest.garbage_level > 80:
                full_bins_count += 1
            total_waste += float(latest.garbage_level)
            total_recyclable += float(latest.recyclable_level)
            total_weight += float(latest.recyclable_weight)
    
    total_payments = Payment.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    unpaid_households = Household.objects.annotate(
        last_payment=Max('payments__payment_date')
    ).filter(
        Q(last_payment__isnull=True) | 
        Q(last_payment__lt=timezone.now() - timedelta(days=30))
    ).count()
    
    context = {
        'total_households': total_households,
        'total_bins': total_bins,
        'active_bins': active_bins,
        'full_bins_count': full_bins_count,
        'total_payments': float(total_payments),
        'total_recyclable_kg': round(total_weight, 2),
        'total_waste_kg': round(total_waste, 1),
        'unpaid_households': unpaid_households,
    }
    
    if user.user_type == 'admin':
        return render(request, 'accounts/dashboard_admin.html', context)
    elif user.user_type == 'collector':
        return render(request, 'accounts/dashboard_collector.html', context)
    else:
        households = Household.objects.filter(user=user)
        
        total_bins_count = SmartBin.objects.filter(household__in=households).count()
        
        bins_data = []
        total_garbage = 0
        total_recyclable_weight = 0
        for hh in households:
            for bin_obj in hh.bins.all():
                latest = bin_obj.iot_data.first()
                if latest:
                    total_garbage += float(latest.garbage_level)
                    total_recyclable_weight += float(latest.recyclable_weight)
                    bins_data.append({
                        'bin_id': bin_obj.bin_id,
                        'status': bin_obj.status,
                        'garbage_level': float(latest.garbage_level),
                        'recyclable_level': float(latest.recyclable_level),
                        'recyclable_weight': float(latest.recyclable_weight),
                        'location_name': bin_obj.location_name or '',
                        'lat': float(bin_obj.latitude),
                        'lng': float(bin_obj.longitude),
                    })
        
        payments = Payment.objects.filter(user=user)
        total_paid = payments.filter(payment_status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        avg_garbage = total_garbage / total_bins_count if total_bins_count > 0 else 0
        estimated_discount = (total_recyclable_weight / 1000) * settings.RECYCLABLE_RATE_PER_KG
        
        hh_context = {
            'total_bins': total_bins_count,
            'total_recyclable_weight': total_recyclable_weight,
            'total_paid': float(total_paid),
            'avg_garbage': avg_garbage,
            'estimated_discount': estimated_discount,
            'bins_data': bins_data,
        }
        return render(request, 'accounts/dashboard_household.html', hh_context)


@login_required
def admin_users(request):
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password')
            user_type = request.POST.get('user_type')
            phone = request.POST.get('phone', '')
            address = request.POST.get('address', '')
            
            if CustomUser.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists')
            else:
                user = CustomUser.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    user_type=user_type,
                    phone=phone,
                    address=address
                )
                messages.success(request, f'User {username} created successfully')
        
        elif action == 'delete':
            user_id = request.POST.get('user_id')
            try:
                user = CustomUser.objects.get(id=user_id)
                if user != request.user:
                    user.delete()
                    messages.success(request, 'User deleted successfully')
            except CustomUser.DoesNotExist:
                messages.error(request, 'User not found')
    
    users = CustomUser.objects.all().order_by('-date_joined')
    admin_count = users.filter(user_type='admin').count()
    collector_count = users.filter(user_type='collector').count()
    household_count = users.filter(user_type='household').count()
    return render(request, 'accounts/admin_users.html', {
        'users': users,
        'admin_count': admin_count,
        'collector_count': collector_count,
        'household_count': household_count
    })


@login_required
def admin_bins(request):
    if request.user.user_type not in ('admin', 'collector'):
        return redirect('dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            bin_id = request.POST.get('bin_id')
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            location_name = request.POST.get('location_name', '')
            household_id = request.POST.get('household')
            collector_id = request.POST.get('collector')
            
            if SmartBin.objects.filter(bin_id=bin_id).exists():
                messages.error(request, 'Bin ID already exists')
            else:
                household = Household.objects.get(id=household_id) if household_id else None
                collector = CustomUser.objects.get(id=collector_id) if collector_id and collector_id != 'None' else None
                
                SmartBin.objects.create(
                    bin_id=bin_id,
                    latitude=latitude,
                    longitude=longitude,
                    location_name=location_name,
                    household=household,
                    assigned_collector=collector
                )
                messages.success(request, f'Bin {bin_id} created successfully')
        
        elif action == 'delete':
            bin_id = request.POST.get('bin_id')
            try:
                bin_obj = SmartBin.objects.get(bin_id=bin_id)
                bin_obj.delete()
                messages.success(request, 'Bin deleted successfully')
            except SmartBin.DoesNotExist:
                messages.error(request, 'Bin not found')
        
        elif action == 'edit':
            old_bin_id = request.POST.get('old_bin_id')
            bin_id = request.POST.get('bin_id')
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            location_name = request.POST.get('location_name')
            household_id = request.POST.get('household')
            collector_id = request.POST.get('collector')
            
            try:
                bin_obj = SmartBin.objects.get(bin_id=old_bin_id)
                bin_obj.bin_id = bin_id
                bin_obj.latitude = latitude
                bin_obj.longitude = longitude
                bin_obj.location_name = location_name
                bin_obj.household = Household.objects.get(id=household_id) if household_id else None
                bin_obj.assigned_collector = CustomUser.objects.get(id=collector_id) if collector_id and collector_id != 'None' else None
                bin_obj.save()
                messages.success(request, 'Bin updated successfully')
            except SmartBin.DoesNotExist:
                messages.error(request, 'Bin not found')
    
    bins = SmartBin.objects.all().order_by('-created_at')
    households = Household.objects.all()
    collectors = CustomUser.objects.filter(user_type='collector')
    
    # Calculate stats
    active_bins = bins.filter(is_active=True).count()
    moderate_bins = 0
    full_bins = 0
    for bin_obj in bins.filter(is_active=True):
        latest = bin_obj.iot_data.first()
        if latest:
            if latest.garbage_level > 80:
                full_bins += 1
            elif latest.garbage_level > 30:
                moderate_bins += 1
    
    return render(request, 'accounts/admin_bins.html', {
        'bins': bins,
        'households': households,
        'collectors': collectors,
        'active_bins': active_bins,
        'moderate_bins': moderate_bins,
        'full_bins': full_bins
    })


@login_required
def admin_households(request):
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            user_id = request.POST.get('user')
            name = request.POST.get('name')
            address = request.POST.get('address')
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            contact_phone = request.POST.get('contact_phone', '')
            
            try:
                user = CustomUser.objects.get(id=user_id)
                if Household.objects.filter(user=user).exists():
                    messages.error(request, 'Household already exists for this user')
                else:
                    Household.objects.create(
                        user=user,
                        name=name,
                        address=address,
                        latitude=latitude,
                        longitude=longitude,
                        contact_phone=contact_phone
                    )
                    messages.success(request, 'Household created successfully')
            except CustomUser.DoesNotExist:
                messages.error(request, 'User not found')
        
        elif action == 'delete':
            household_id = request.POST.get('household_id')
            try:
                household = Household.objects.get(id=household_id)
                household.delete()
                messages.success(request, 'Household deleted successfully')
            except Household.DoesNotExist:
                messages.error(request, 'Household not found')
        
        elif action == 'edit':
            household_id = request.POST.get('household_id')
            name = request.POST.get('name')
            address = request.POST.get('address')
            contact_phone = request.POST.get('contact_phone')
            
            try:
                household = Household.objects.get(id=household_id)
                household.name = name
                household.address = address
                household.contact_phone = contact_phone
                household.save()
                messages.success(request, 'Household updated successfully')
            except Household.DoesNotExist:
                messages.error(request, 'Household not found')
    
    households = Household.objects.all().order_by('-created_at')
    users = CustomUser.objects.filter(user_type='household')
    
    # Calculate stats
    households_with_bins = households.filter(bins__isnull=False).distinct().count()
    thirty_days_ago = timezone.now() - timedelta(days=30)
    unpaid_households = households.annotate(
        last_payment=Max('payments__payment_date')
    ).filter(
        Q(last_payment__isnull=True) | 
        Q(last_payment__lt=thirty_days_ago)
    ).count()
    
    return render(request, 'accounts/admin_households.html', {
        'households': households,
        'users': users,
        'households_with_bins': households_with_bins,
        'unpaid_households': unpaid_households
    })


@login_required
def admin_payments(request):
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    payments = Payment.objects.all().order_by('-payment_date')
    
    # Get payment stats
    total_payments = payments.count()
    total_amount = payments.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    completed_payments = payments.filter(payment_status='completed').count()
    pending_payments = payments.filter(payment_status='pending').count()
    
    # Get household payment summary
    households_with_payments = []
    for hh in Household.objects.all():
        hh_payments = hh.payments.all()
        if hh_payments.exists():
            total_paid = hh_payments.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
            last_payment = hh_payments.order_by('-payment_date').first()
            households_with_payments.append({
                'name': hh.name,
                'user': hh.user,
                'total_paid': total_paid,
                'payment_count': hh_payments.count(),
                'last_payment_date': last_payment.payment_date if last_payment else None,
                'days_since_payment': (timezone.now() - last_payment.payment_date).days if last_payment else 999
            })
    
    return render(request, 'accounts/admin_payments.html', {
        'payments': payments,
        'total_payments': total_payments,
        'total_amount': total_amount,
        'completed_payments': completed_payments,
        'pending_payments': pending_payments,
        'households_with_payments': households_with_payments
    })


@login_required
def admin_payment_recipients(request):
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    # Get all households with their payment info
    recipients = []
    for hh in Household.objects.all().order_by('name'):
        hh_payments = hh.payments.all()
        total_paid = hh_payments.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        pending_amount = hh_payments.filter(payment_status='pending').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        last_payment = hh_payments.order_by('-payment_date').first()
        bin_count = hh.bins.count()
        
        recipients.append({
            'id': hh.id,
            'name': hh.name,
            'address': hh.address,
            'contact_phone': hh.contact_phone,
            'user': hh.user,
            'bin_count': bin_count,
            'total_paid': total_paid,
            'pending_amount': pending_amount,
            'payment_count': hh_payments.count(),
            'last_payment_date': last_payment.payment_date if last_payment else None,
            'days_since_payment': (timezone.now() - last_payment.payment_date).days if last_payment else 999,
            'has_overdue': last_payment and (timezone.now() - last_payment.payment_date).days > 30
        })
    
    total_recipients = len(recipients)
    active_recipients = sum(1 for r in recipients if r['payment_count'] > 0)
    overdue_recipients = sum(1 for r in recipients if r['has_overdue'])
    no_payment_recipients = sum(1 for r in recipients if r['payment_count'] == 0)
    
    return render(request, 'accounts/admin_payment_recipients.html', {
        'recipients': recipients,
        'total_recipients': total_recipients,
        'active_recipients': active_recipients,
        'overdue_recipients': overdue_recipients,
        'no_payment_recipients': no_payment_recipients,
    })


@login_required
def admin_routes(request):
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    collectors = CustomUser.objects.filter(user_type='collector')
    
    all_bins = SmartBin.objects.filter(is_active=True)
    full_bins_list = []
    for bin_obj in all_bins:
        latest = bin_obj.iot_data.first()
        if latest and latest.garbage_level > 80:
            full_bins_list.append({
                'obj': bin_obj,
                'garbage_level': float(latest.garbage_level),
            })
    
    unassigned_full_list = []
    for fb in full_bins_list:
        if not fb['obj'].assigned_collector:
            unassigned_full_list.append(fb['obj'])
    
    collector_routes = []
    for collector in collectors:
        assigned_bins = SmartBin.objects.filter(assigned_collector=collector, is_active=True)
        collector_full = []
        for bin_obj in assigned_bins:
            latest = bin_obj.iot_data.first()
            if latest and latest.garbage_level > 80:
                collector_full.append({
                    'bin_id': bin_obj.bin_id,
                    'lat': float(bin_obj.latitude),
                    'lng': float(bin_obj.longitude),
                    'garbage_level': float(latest.garbage_level),
                    'location_name': bin_obj.location_name or 'Unknown',
                    'household_name': bin_obj.household.name if bin_obj.household else 'N/A',
                    'bin_obj': bin_obj,
                })
        
        if collector_full:
            depot_lat, depot_lng = _get_collector_depot(collector)
            sorted_bins = clarke_wright_savings(collector_full, depot_lat, depot_lng)
            total_dist = calculate_total_distance(sorted_bins)
        else:
            sorted_bins = []
            total_dist = 0
        
        collector_routes.append({
            'collector': collector,
            'full_bins': collector_full,
            'sorted_route': sorted_bins,
            'total_distance': total_dist,
            'full_count': len(collector_full),
        })
    
    return render(request, 'accounts/admin_routes.html', {
        'collectors': collectors,
        'full_bins': full_bins_list,
        'full_bins_count': len(full_bins_list),
        'collector_routes': collector_routes,
        'unassigned_full_bins': unassigned_full_list,
        'unassigned_count': len(unassigned_full_list),
    })


@login_required
def payments_page(request):
    user = request.user
    if user.user_type not in ['household', 'admin', 'collector']:
        return redirect('dashboard')
    return render(request, 'payments/index.html')


@login_required
def reports_page(request):
    user = request.user
    if user.user_type not in ['admin', 'collector']:
        return redirect('dashboard')
    return render(request, 'reports/index.html')


@login_required
def profile_page(request):
    if request.method == 'POST':
        user = request.user

        if request.POST.get('change_password'):
            old = request.POST.get('old_password', '')
            new1 = request.POST.get('new_password1', '')
            new2 = request.POST.get('new_password2', '')
            if not user.check_password(old):
                messages.error(request, 'Current password is incorrect')
            elif new1 != new2:
                messages.error(request, 'New passwords do not match')
            elif len(new1) < 6:
                messages.error(request, 'New password must be at least 6 characters')
            else:
                user.set_password(new1)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Password changed successfully')
            return redirect('profile')

        if request.POST.get('save_household'):
            household_id = request.POST.get('household_id')
            household = get_object_or_404(Household, id=household_id, user=user)
            household.name = request.POST.get('hh_name', household.name)
            household.address = request.POST.get('hh_address', household.address)
            household.contact_phone = request.POST.get('hh_phone', household.contact_phone)
            if request.FILES.get('hh_photo'):
                household.passport_photo = request.FILES.get('hh_photo')
            household.save()
            messages.success(request, 'Household information updated successfully')
            return redirect('profile')

        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone)
        user.address = request.POST.get('address', user.address)
        if request.FILES.get('profile_image'):
            user.profile_image = request.FILES.get('profile_image')
        user.save()
        messages.success(request, 'Profile updated successfully')
        return redirect('profile')
    
    households = Household.objects.filter(user=request.user)
    return render(request, 'accounts/profile.html', {
        'households': households
    })


@login_required
def household_page(request):
    households = Household.objects.filter(user=request.user)
    all_bins = []
    for hh in households:
        bins = hh.bins.all()
        for bin in bins:
            all_bins.append({
                'id': bin.id,
                'bin_id': bin.bin_id,
                'location': bin.location_name,
                'garbage_level': bin.current_garbage_level,
                'recyclable_level': bin.current_recyclable_level,
                'status': bin.get_status_display() if hasattr(bin, 'get_status_display') else bin.status,
                'latitude': float(bin.latitude),
                'longitude': float(bin.longitude),
            })
    return render(request, 'accounts/household.html', {
        'households': households,
        'bins': all_bins
    })


@login_required
def edit_bin(request, bin_id):
    bin_obj = get_object_or_404(SmartBin, id=bin_id)
    households = Household.objects.filter(user=request.user)
    if bin_obj.household not in households:
        messages.error(request, 'You can only edit your own bins')
        return redirect('household')

    if request.method == 'POST':
        bin_obj.location_name = request.POST.get('location_name', bin_obj.location_name)
        bin_obj.latitude = request.POST.get('latitude', bin_obj.latitude)
        bin_obj.longitude = request.POST.get('longitude', bin_obj.longitude)
        bin_obj.save()
        messages.success(request, f'Bin {bin_obj.bin_id} updated successfully')
        return redirect('household')

    return render(request, 'accounts/edit_bin.html', {
        'bin': bin_obj,
        'households': households,
    })


class RegisterView(APIView):
    def post(self, request):
        data = request.data
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        user_type = data.get('user_type', 'household')
        
        if CustomUser.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = CustomUser.objects.create_user(
            username=username,
            password=password,
            email=email,
            user_type=user_type,
            phone=data.get('phone', ''),
            address=data.get('address', ''),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
        )
        
        return Response({
            'success': True,
            'user_id': user.id,
            'username': user.username
        }, status=status.HTTP_201_CREATED)


class HouseholdListView(APIView):
    def get(self, request):
        households = Household.objects.all()
        data = []
        for hh in households:
            data.append({
                'id': hh.id,
                'name': hh.name,
                'address': hh.address,
                'latitude': float(hh.latitude) if hh.latitude else None,
                'longitude': float(hh.longitude) if hh.longitude else None,
                'contact_phone': hh.contact_phone,
                'user': hh.user.username,
            })
        return Response(data)
    
    def post(self, request):
        data = request.data
        user = request.user
        
        household = Household.objects.create(
            user=user,
            name=data.get('name'),
            address=data.get('address'),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            contact_phone=data.get('contact_phone', ''),
        )
        
        return Response({
            'success': True,
            'household_id': household.id
        }, status=status.HTTP_201_CREATED)


class HouseholdDetailView(APIView):
    def get(self, request, pk):
        household = get_object_or_404(Household, pk=pk)
        bins = household.bins.all()
        data = {
            'id': household.id,
            'name': household.name,
            'address': household.address,
            'latitude': float(household.latitude) if household.latitude else None,
            'longitude': float(household.longitude) if household.longitude else None,
            'contact_phone': household.contact_phone,
            'user': household.user.username,
            'bins': [{'bin_id': b.bin_id} for b in bins],
        }
        return Response(data)


class AdminStatsView(APIView):
    def get(self, request):
        total_households = Household.objects.count()
        total_bins = SmartBin.objects.count()
        active_bins = SmartBin.objects.filter(is_active=True).count()
        
        full_bins = 0
        for bin_obj in SmartBin.objects.filter(is_active=True):
            latest = bin_obj.iot_data.first()
            if latest and latest.garbage_level > 80:
                full_bins += 1
        
        total_payments = Payment.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        total_weight = 0
        for bin_obj in SmartBin.objects.filter(is_active=True):
            latest = bin_obj.iot_data.first()
            if latest:
                total_weight += float(latest.recyclable_weight)
        
        unpaid_households = Household.objects.annotate(
            last_payment=Max('payments__payment_date')
        ).filter(
            Q(last_payment__isnull=True) | 
            Q(last_payment__lt=timezone.now() - timedelta(days=30))
        ).count()
        
        return Response({
            'total_households': total_households,
            'total_bins': total_bins,
            'active_bins': active_bins,
            'full_bins': full_bins,
            'total_payments': float(total_payments),
            'total_recyclable_kg': round(total_weight, 2),
            'total_waste_kg': 0,
            'unpaid_households': unpaid_households,
        })


class CollectorStatsView(APIView):
    def get(self, request):
        user = request.user
        
        assigned_bins = SmartBin.objects.filter(assigned_collector=user)
        
        full_bins = []
        for bin_obj in assigned_bins:
            latest = bin_obj.iot_data.first()
            if latest and latest.garbage_level > 80:
                full_bins.append({
                    'bin_id': bin_obj.bin_id,
                    'lat': float(bin_obj.latitude),
                    'lng': float(bin_obj.longitude),
                    'garbage_level': float(latest.garbage_level),
                })
        
        return Response({
            'assigned_bins_count': assigned_bins.count(),
            'full_bins_count': len(full_bins),
            'full_bins': full_bins,
        })


class HouseholdStatsView(APIView):
    def get(self, request):
        user = request.user
        
        households = Household.objects.filter(user=user)
        total_bins = SmartBin.objects.filter(household__in=households).count()
        
        bins_data = []
        total_garbage = 0
        total_recyclable = 0
        total_weight = 0
        
        for hh in households:
            for bin_obj in hh.bins.all():
                latest = bin_obj.iot_data.first()
                if latest:
                    total_garbage += float(latest.garbage_level)
                    total_recyclable += float(latest.recyclable_level)
                    total_weight += float(latest.recyclable_weight)
                    bins_data.append({
                        'bin_id': bin_obj.bin_id,
                        'lat': float(bin_obj.latitude),
                        'lng': float(bin_obj.longitude),
                        'garbage_level': float(latest.garbage_level),
                        'recyclable_level': float(latest.recyclable_level),
                        'recyclable_weight': float(latest.recyclable_weight),
                    })
        
        payments = Payment.objects.filter(user=user)
        total_paid = payments.filter(payment_status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        return Response({
            'households_count': households.count(),
            'total_bins': total_bins,
            'bins': bins_data,
            'avg_garbage': total_garbage / total_bins if total_bins > 0 else 0,
            'avg_recyclable': total_recyclable / total_bins if total_bins > 0 else 0,
            'total_recyclable_weight': total_weight,
            'total_paid': float(total_paid),
        })


@login_required
@login_required
def register_bin(request):
    if request.user.user_type not in ('admin', 'collector'):
        messages.error(request, 'You do not have permission to register bins')
        return redirect('dashboard')

    households = Household.objects.all()
    selected_household = None

    if request.method == 'POST':
        bin_id = request.POST.get('bin_id')
        latitude = request.POST.get('latitude') or 0
        longitude = request.POST.get('longitude') or 0
        location_name = request.POST.get('location_name', '')
        household_id = request.POST.get('household')

        if not bin_id:
            messages.error(request, 'Bin ID is required')
            return redirect('register_bin')

        if SmartBin.objects.filter(bin_id=bin_id).exists():
            messages.error(request, 'Bin ID already exists')
            return redirect('register_bin')

        household = get_object_or_404(Household, id=household_id) if household_id else None

        SmartBin.objects.create(
            bin_id=bin_id,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name or f'Bin at {latitude}, {longitude}',
            household=household,
        )
        messages.success(request, f'Bin {bin_id} registered successfully')
        return redirect('admin_bins')

    return render(request, 'accounts/register_bin.html', {
        'households': households
    })


@login_required
def collector_bins(request):
    if request.user.user_type != 'collector':
        return redirect('dashboard')
    return render(request, 'accounts/collector_bins.html')


@login_required
def collector_schedules(request):
    if request.user.user_type != 'collector':
        return redirect('dashboard')

    households = Household.objects.all()
    bins = SmartBin.objects.filter(is_active=True)

    if request.method == 'POST':
        household_id = request.POST.get('household_id')
        bin_id = request.POST.get('bin_id')
        scheduled_date = request.POST.get('scheduled_date')
        time_slot = request.POST.get('time_slot', 'morning')
        notes = request.POST.get('notes', '')

        if household_id and scheduled_date:
            household = get_object_or_404(Household, id=household_id)
            bin_obj = None
            if bin_id:
                bin_obj = get_object_or_404(SmartBin, id=bin_id)
            CollectionSchedule.objects.create(
                collector=request.user,
                household=household,
                bin=bin_obj,
                scheduled_date=scheduled_date,
                time_slot=time_slot,
                notes=notes,
            )
            messages.success(request, f'Collection scheduled for {household.name} on {scheduled_date}')
        else:
            messages.error(request, 'Household and scheduled date are required')
        return redirect('collector_schedules')

    schedules = CollectionSchedule.objects.all().order_by('-scheduled_date', '-created_at')

    return render(request, 'accounts/collector_schedules.html', {
        'schedules': schedules,
        'households': households,
        'bins': bins,
        'today': timezone.now(),
    })


@login_required
def household_schedules(request):
    if request.user.user_type != 'household':
        return redirect('dashboard')

    schedules = CollectionSchedule.objects.all().order_by('-scheduled_date', '-created_at')

    return render(request, 'accounts/household_schedules.html', {
        'schedules': schedules,
    })


@login_required
def admin_schedules(request):
    if request.user.user_type != 'admin':
        return redirect('dashboard')

    schedules = CollectionSchedule.objects.all().order_by('-scheduled_date', '-created_at')

    collectors = CustomUser.objects.filter(user_type='collector')
    households = Household.objects.all()

    if request.method == 'POST':
        action = request.POST.get('action')
        schedule_id = request.POST.get('schedule_id')
        schedule = get_object_or_404(CollectionSchedule, id=schedule_id)
        if action == 'complete':
            schedule.status = 'completed'
        elif action == 'cancel':
            schedule.status = 'cancelled'
        schedule.save()
        messages.success(request, f'Schedule #{schedule.id} updated to {schedule.status}')
        return redirect('admin_schedules')

    return render(request, 'accounts/admin_schedules.html', {
        'schedules': schedules,
        'collectors': collectors,
        'households': households,
        'schedules_in_progress': schedules.filter(status='in_progress').count(),
        'schedules_completed': schedules.filter(status='completed').count(),
        'schedules_cancelled': schedules.filter(status='cancelled').count(),
    })


class UserListView(APIView):
    def get(self, request):
        if request.user.user_type != 'admin':
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        users = CustomUser.objects.all()
        data = []
        for user in users:
            data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'user_type': user.user_type,
                'is_active': user.is_active,
                'date_joined': user.date_joined.isoformat(),
            })
        return Response(data)