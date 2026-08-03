from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view
from django.shortcuts import render
from django.db.models import Count, Sum, Avg, Max, Min
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import math
from bins.models import SmartBin, IoTData
from accounts.models import Household, CustomUser
from payments.models import Payment, Receipt
from .models import CollectionRoute, Notification, CollectionSchedule
from django.http import HttpResponse
import csv
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

_distance_cache = {}


class DashboardStatsView(APIView):
    def get(self, request):
        total_bins = SmartBin.objects.count()
        active_bins = SmartBin.objects.filter(is_active=True).count()
        full_bins = 0
        
        for bin_obj in SmartBin.objects.filter(is_active=True):
            latest = bin_obj.iot_data.first()
            if latest and latest.garbage_level > 80:
                full_bins += 1
        
        total_households = Household.objects.count()
        total_collections = IoTData.objects.count()
        
        total_payments = Payment.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_recyclable = IoTData.objects.aggregate(Sum('recyclable_weight'))['recyclable_weight__sum'] or 0
        
        return Response({
            'total_bins': total_bins,
            'active_bins': active_bins,
            'full_bins': full_bins,
            'total_households': total_households,
            'total_collections': total_collections,
            'total_payments': float(total_payments),
            'total_recyclable_kg': float(total_recyclable),
        })


class WasteTrendsView(APIView):
    def get(self, request):
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        data = IoTData.objects.filter(timestamp__gte=start_date).values('timestamp__date').annotate(
            avg_garbage=Avg('garbage_level'),
            avg_recyclable=Avg('recyclable_level'),
            total_weight=Sum('recyclable_weight'),
        ).order_by('timestamp__date')
        
        result = []
        for item in data:
            result.append({
                'date': str(item['timestamp__date']),
                'avg_garbage': float(item['avg_garbage']),
                'avg_recyclable': float(item['avg_recyclable']),
                'total_weight': float(item['total_weight']),
            })
        
        return Response(result)


class BinUsageStatsView(APIView):
    def get(self, request):
        bins = SmartBin.objects.all()
        data = []
        
        for bin_obj in bins:
            iot_entries = bin_obj.iot_data.all()
            data.append({
                'bin_id': bin_obj.bin_id,
                'total_readings': iot_entries.count(),
                'avg_garbage': float(iot_entries.aggregate(Avg('garbage_level'))['garbage_level__avg'] or 0),
                'avg_recyclable': float(iot_entries.aggregate(Avg('recyclable_level'))['recyclable_level__avg'] or 0),
                'total_recyclable_kg': float(iot_entries.aggregate(Sum('recyclable_weight'))['recyclable_weight__sum'] or 0),
            })
        
        return Response(data)


class PaymentSummaryView(APIView):
    def get(self, request):
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        payments = Payment.objects.filter(payment_date__gte=start_date)
        
        data = {
            'total_transactions': payments.count(),
            'total_amount': float(payments.aggregate(Sum('total_amount'))['total_amount__sum'] or 0),
            'total_discount': float(payments.aggregate(Sum('recyclable_discount'))['recyclable_discount__sum'] or 0),
            'average_amount': float(payments.aggregate(Avg('total_amount'))['total_amount__avg'] or 0),
        }
        
        return Response(data)


class RecyclableStatsView(APIView):
    def get(self, request):
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        data = IoTData.objects.filter(timestamp__gte=start_date).aggregate(
            total_kg=Sum('recyclable_weight'),
            avg_level=Avg('recyclable_level'),
            max_weight=Max('recyclable_weight'),
        )
        
        return Response({
            'total_kg': float(data['total_kg'] or 0),
            'avg_level': float(data['avg_level'] or 0),
            'max_weight': float(data['max_weight'] or 0),
        })


def _cache_key(lat1, lng1, lat2, lng2):
    return (round(float(lat1), 6), round(float(lng1), 6),
            round(float(lat2), 6), round(float(lng2), 6))


def _get_distance(b1, b2):
    key = _cache_key(b1['lat'], b1['lng'], b2['lat'], b2['lng'])
    if key in _distance_cache:
        return _distance_cache[key]
    dist = haversine_distance(b1['lat'], b1['lng'], b2['lat'], b2['lng'])
    _distance_cache[key] = dist
    return dist


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def calculate_total_distance(bins):
    if len(bins) < 2:
        return 0
    total = 0
    for i in range(len(bins) - 1):
        total += _get_distance(bins[i], bins[i + 1])
    return round(total, 2)


def clarke_wright_savings(bins, depot_lat, depot_lng):
    n = len(bins)
    if n < 2:
        return bins

    depot_dists = [haversine_distance(depot_lat, depot_lng, b['lat'], b['lng']) for b in bins]

    savings = []
    for i in range(n):
        for j in range(i + 1, n):
            saving = depot_dists[i] + depot_dists[j] - _get_distance(bins[i], bins[j])
            savings.append((saving, i, j))

    savings.sort(key=lambda x: x[0], reverse=True)

    route_of = list(range(n))
    routes = [[i] for i in range(n)]
    start_of = list(range(n))
    end_of = list(range(n))

    for saving, i, j in savings:
        if saving <= 0:
            break

        ri, rj = route_of[i], route_of[j]
        if ri == rj:
            continue

        if end_of[ri] == i and start_of[rj] == j:
            routes[ri].extend(routes[rj])
            for idx in routes[rj]:
                route_of[idx] = ri
            routes[rj] = []
            end_of[ri] = end_of[rj]
        elif end_of[rj] == j and start_of[ri] == i:
            routes[rj].extend(routes[ri])
            for idx in routes[ri]:
                route_of[idx] = rj
            routes[ri] = []
            end_of[rj] = end_of[ri]

    final_routes = [r for r in routes if r]
    if not final_routes:
        return []

    main_route = max(final_routes, key=len)
    main_route.sort(key=lambda idx: bins[idx].get('garbage_level', 0), reverse=True)

    return [bins[idx] for idx in main_route]


Iyunga_CENTER_LAT = -8.899
Iyunga_CENTER_LNG = 33.454


def _get_collector_depot(collector):
    lat = float(collector.latitude) if collector.latitude else Iyunga_CENTER_LAT
    lng = float(collector.longitude) if collector.longitude else Iyunga_CENTER_LNG
    return lat, lng


@api_view(['GET'])
def optimize_route(request):
    full_bins = []
    for bin_obj in SmartBin.objects.filter(is_active=True):
        latest = bin_obj.iot_data.first()
        if latest and latest.garbage_level > 80:
            full_bins.append({
                'bin_id': bin_obj.bin_id,
                'lat': float(bin_obj.latitude),
                'lng': float(bin_obj.longitude),
                'garbage_level': float(latest.garbage_level),
                'location_name': bin_obj.location_name or 'Unknown',
                'assigned_collector': bin_obj.assigned_collector.username if bin_obj.assigned_collector else None,
            })

    if not full_bins:
        return Response({'route': [], 'total_distance': 0})

    if len(full_bins) == 1:
        return Response({'route': full_bins, 'total_distance': 0, 'bin_count': 1, 'depot': {'lat': Iyunga_CENTER_LAT, 'lng': Iyunga_CENTER_LNG}})

    sorted_bins = clarke_wright_savings(full_bins, Iyunga_CENTER_LAT, Iyunga_CENTER_LNG)
    total_distance = calculate_total_distance(sorted_bins)

    return Response({
        'route': sorted_bins,
        'total_distance': total_distance,
        'bin_count': len(sorted_bins),
        'depot': {'lat': Iyunga_CENTER_LAT, 'lng': Iyunga_CENTER_LNG}
    })


def export_csv(request):
    bins = SmartBin.objects.all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bins_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Bin ID', 'Latitude', 'Longitude', 'Status', 'Garbage Level', 'Recyclable Level', 'Recyclable Weight'])
    
    for bin_obj in bins:
        latest = bin_obj.iot_data.first()
        writer.writerow([
            bin_obj.bin_id,
            bin_obj.latitude,
            bin_obj.longitude,
            bin_obj.status,
            latest.garbage_level if latest else 0,
            latest.recyclable_level if latest else 0,
            latest.recyclable_weight if latest else 0,
        ])
    
    return response


def export_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="report.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph("Waste Collection Report", styles['Title']))
    elements.append(Spacer(1, 12))
    
    data = [['Bin ID', 'Garbage %', 'Recyclable %', 'Weight (kg)']]
    
    for bin_obj in SmartBin.objects.all()[:50]:
        latest = bin_obj.iot_data.first()
        data.append([
            bin_obj.bin_id,
            f"{latest.garbage_level if latest else 0}",
            f"{latest.recyclable_level if latest else 0}",
            f"{latest.recyclable_weight if latest else 0}",
        ])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    return response


@api_view(['GET'])
def optimize_collector_route(request):
    if not request.user.is_authenticated or request.user.user_type != 'collector':
        return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

    user = request.user
    depot_lat, depot_lng = _get_collector_depot(user)
    assigned_bins = SmartBin.objects.filter(assigned_collector=user, is_active=True)

    all_bins = []
    for bin_obj in assigned_bins:
        latest = bin_obj.iot_data.first()
        if latest and latest.garbage_level > 80:
            all_bins.append({
                'bin_id': bin_obj.bin_id,
                'lat': float(bin_obj.latitude),
                'lng': float(bin_obj.longitude),
                'garbage_level': float(latest.garbage_level),
                'location_name': bin_obj.location_name or 'Unknown',
            })

    if not all_bins:
        return Response({'route': [], 'total_distance': 0, 'message': 'No full bins to collect'})

    if len(all_bins) == 1:
        return Response({'route': all_bins, 'total_distance': 0, 'bin_count': 1, 'depot': {'lat': depot_lat, 'lng': depot_lng}})

    sorted_bins = clarke_wright_savings(all_bins, depot_lat, depot_lng)
    total_distance = calculate_total_distance(sorted_bins)

    return Response({
        'route': sorted_bins,
        'total_distance': total_distance,
        'bin_count': len(sorted_bins),
        'depot': {'lat': depot_lat, 'lng': depot_lng}
    })


class CollectorSchedulesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != 'collector':
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        schedules = CollectionSchedule.objects.all().order_by('-scheduled_date', '-created_at')
        data = []
        for s in schedules:
            data.append({
                'id': s.id,
                'household_name': s.household.name,
                'household_address': s.household.address,
                'household_phone': s.household.contact_phone,
                'bin_id': s.bin.bin_id if s.bin else None,
                'scheduled_date': s.scheduled_date.isoformat(),
                'time_slot': s.time_slot,
                'status': s.status,
                'notes': s.notes,
                'created_at': s.created_at.isoformat(),
            })
        return Response(data)

    def post(self, request):
        if request.user.user_type != 'collector':
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        household_id = request.data.get('household_id')
        bin_id = request.data.get('bin_id')
        scheduled_date = request.data.get('scheduled_date')
        time_slot = request.data.get('time_slot', 'morning')
        notes = request.data.get('notes', '')

        if not household_id or not scheduled_date:
            return Response({'error': 'Household and scheduled date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            household = Household.objects.get(id=household_id)
        except Household.DoesNotExist:
            return Response({'error': 'Household not found'}, status=status.HTTP_404_NOT_FOUND)

        bin_obj = None
        if bin_id:
            try:
                bin_obj = SmartBin.objects.get(id=bin_id)
            except SmartBin.DoesNotExist:
                pass

        schedule = CollectionSchedule.objects.create(
            collector=request.user,
            household=household,
            bin=bin_obj,
            scheduled_date=scheduled_date,
            time_slot=time_slot,
            notes=notes,
        )

        return Response({
            'id': schedule.id,
            'success': True,
            'message': f'Schedule created for {household.name} on {scheduled_date}'
        }, status=status.HTTP_201_CREATED)


class UpdateScheduleStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, schedule_id):
        try:
            schedule = CollectionSchedule.objects.get(id=schedule_id)
        except CollectionSchedule.DoesNotExist:
            return Response({'error': 'Schedule not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.user_type == 'collector' and schedule.collector != request.user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.user_type not in ['collector', 'admin']:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')
        if new_status not in dict(CollectionSchedule.STATUS_CHOICES):
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

        schedule.status = new_status
        schedule.save()

        return Response({
            'success': True,
            'id': schedule.id,
            'status': schedule.status,
        })


class HouseholdSchedulesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != 'household':
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        schedules = CollectionSchedule.objects.all().order_by('-scheduled_date', '-created_at')
        data = []
        for s in schedules:
            data.append({
                'id': s.id,
                'collector_name': s.collector.username,
                'collector_phone': s.collector.phone,
                'household_name': s.household.name,
                'bin_id': s.bin.bin_id if s.bin else None,
                'scheduled_date': s.scheduled_date.isoformat(),
                'time_slot': s.time_slot,
                'status': s.status,
                'notes': s.notes,
                'created_at': s.created_at.isoformat(),
            })
        return Response(data)


class AdminSchedulesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != 'admin':
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        schedules = CollectionSchedule.objects.all().order_by('-scheduled_date', '-created_at')
        data = []
        for s in schedules:
            data.append({
                'id': s.id,
                'collector_name': s.collector.username,
                'collector_phone': s.collector.phone,
                'household_name': s.household.name,
                'household_address': s.household.address,
                'household_phone': s.household.contact_phone,
                'bin_id': s.bin.bin_id if s.bin else None,
                'scheduled_date': s.scheduled_date.isoformat(),
                'time_slot': s.time_slot,
                'status': s.status,
                'notes': s.notes,
                'created_at': s.created_at.isoformat(),
            })
        return Response(data)