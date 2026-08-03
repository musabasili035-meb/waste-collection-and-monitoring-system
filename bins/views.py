from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from .models import SmartBin, IoTData
from accounts.models import Household
from reports.models import Notification
import json
from django.utils import timezone
from datetime import timedelta


class IoTDataReceiveView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        bin_id = data.get('bin_id')
        
        if not bin_id:
            return Response({'error': 'bin_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        bin_obj, created = SmartBin.objects.get_or_create(
            bin_id=bin_id,
            defaults={
                'latitude': data.get('latitude', 0),
                'longitude': data.get('longitude', 0),
            }
        )

        if not created:
            new_lat = data.get('latitude', 0)
            new_lon = data.get('longitude', 0)
            if new_lat and new_lat != 0:
                bin_obj.latitude = new_lat
                bin_obj.longitude = new_lon
                bin_obj.save(update_fields=['latitude', 'longitude'])

        iot_data = IoTData.objects.create(
            bin=bin_obj,
            garbage_level=data.get('waste_level', data.get('garbage_level', 0)),
            recyclable_level=data.get('recycle_level', data.get('recyclable_level', 0)),
            recyclable_weight=data.get('recycle_weight', data.get('recyclable_weight', 0)),
            latitude=data.get('latitude', 0),
            longitude=data.get('longitude', 0)
        )
        
        if iot_data.garbage_level > 80:
            Notification.objects.create(
                notification_type='bin_full',
                title=f'Bin {bin_id} is Full',
                message=f'Bin {bin_id} has reached {iot_data.garbage_level}% capacity. Immediate collection required.'
            )
        
        return Response({
            'success': True,
            'message': 'Data received successfully',
            'data_id': iot_data.id
        }, status=status.HTTP_201_CREATED)


class BinListView(generics.ListCreateAPIView):
    queryset = SmartBin.objects.all()
    serializer_class = None


class BinDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = SmartBin.objects.all()
    serializer_class = None


class BinStatusView(APIView):
    def get(self, request):
        bins = SmartBin.objects.all()
        bin_data = []
        for bin_obj in bins:
            latest = bin_obj.iot_data.first()
            bin_data.append({
                'bin_id': bin_obj.bin_id,
                'latitude': float(bin_obj.latitude),
                'longitude': float(bin_obj.longitude),
                'status': bin_obj.status,
                'garbage_level': float(latest.garbage_level) if latest else 0,
                'recyclable_level': float(latest.recyclable_level) if latest else 0,
                'recyclable_weight': float(latest.recyclable_weight) if latest else 0,
            })
        return Response(bin_data)


class BinMapDataView(APIView):
    permission_classes = []
    
    def get(self, request):
        bins = SmartBin.objects.filter(is_active=True)
        data = []
        for bin_obj in bins:
            latest = bin_obj.iot_data.first()
            garbage = float(latest.garbage_level) if latest else 0
            recyclable = float(latest.recyclable_level) if latest else 0
            weight = float(latest.recyclable_weight) if latest else 0
            
            if garbage > 80:
                bin_status = 'Full'
            elif garbage > 30:
                bin_status = 'Moderate'
            else:
                bin_status = 'Empty'
            
            data.append({
                'id': bin_obj.id,
                'bin_id': bin_obj.bin_id,
                'lat': float(bin_obj.latitude),
                'lng': float(bin_obj.longitude),
                'garbage_level': garbage,
                'recyclable_level': recyclable,
                'recyclable_weight': weight,
                'status': bin_status,
                'location_name': bin_obj.location_name,
                'household_name': bin_obj.household.name if bin_obj.household else None,
                'collector_name': bin_obj.assigned_collector.username if bin_obj.assigned_collector else None,
            })
        return Response(data)


class CollectorBinsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        bins = SmartBin.objects.filter(assigned_collector=user, is_active=True)
        data = []
        for bin_obj in bins:
            latest = bin_obj.iot_data.first()
            garbage = float(latest.garbage_level) if latest else 0
            recyclable = float(latest.recyclable_level) if latest else 0
            weight = float(latest.recyclable_weight) if latest else 0
            
            if garbage > 80:
                bin_status = 'Full'
            elif garbage > 30:
                bin_status = 'Moderate'
            else:
                bin_status = 'Empty'
            
            data.append({
                'bin_id': bin_obj.bin_id,
                'lat': float(bin_obj.latitude),
                'lng': float(bin_obj.longitude),
                'garbage_level': garbage,
                'recyclable_level': recyclable,
                'recyclable_weight': weight,
                'status': bin_status,
                'location_name': bin_obj.location_name,
                'household_name': bin_obj.household.name if bin_obj.household else None,
            })
        return Response(data)


class HouseholdBinsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        households = Household.objects.filter(user=user)
        bins = SmartBin.objects.filter(household__in=households, is_active=True)
        data = []
        for bin_obj in bins:
            latest = bin_obj.iot_data.first()
            garbage = float(latest.garbage_level) if latest else 0
            recyclable = float(latest.recyclable_level) if latest else 0
            weight = float(latest.recyclable_weight) if latest else 0
            
            if garbage > 80:
                bin_status = 'Full'
            elif garbage > 30:
                bin_status = 'Moderate'
            else:
                bin_status = 'Empty'
            
            data.append({
                'bin_id': bin_obj.bin_id,
                'lat': float(bin_obj.latitude),
                'lng': float(bin_obj.longitude),
                'garbage_level': garbage,
                'recyclable_level': recyclable,
                'recyclable_weight': weight,
                'status': bin_status,
                'location_name': bin_obj.location_name,
            })
        return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_bin_collected(request):
    bin_id = request.data.get('bin_id')
    if not bin_id:
        return Response({'error': 'bin_id required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        bin_obj = SmartBin.objects.get(bin_id=bin_id)
        if request.user != bin_obj.assigned_collector and request.user.user_type != 'admin':
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        
        IoTData.objects.create(
            bin=bin_obj,
            garbage_level=0,
            recyclable_level=0,
            recyclable_weight=0,
            latitude=bin_obj.latitude,
            longitude=bin_obj.longitude
        )
        
        return Response({'success': True, 'message': 'Bin marked as collected'})
    except SmartBin.DoesNotExist:
        return Response({'error': 'Bin not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_bin_issue(request):
    bin_id = request.data.get('bin_id')
    issue_type = request.data.get('issue_type')
    description = request.data.get('description', '')
    
    if not bin_id or not issue_type:
        return Response({'error': 'bin_id and issue_type required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        bin_obj = SmartBin.objects.get(bin_id=bin_id)
        Notification.objects.create(
            notification_type=f'issue_{issue_type}',
            title=f'Issue reported: {issue_type}',
            message=f'Bin {bin_id}: {description}',
            is_read=False
        )
        return Response({'success': True, 'message': 'Issue reported'})
    except SmartBin.DoesNotExist:
        return Response({'error': 'Bin not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def get_full_bins(request):
    bins = SmartBin.objects.filter(is_active=True)
    full_bins = []
    for bin_obj in bins:
        latest = bin_obj.iot_data.first()
        if latest and latest.garbage_level > 80:
            full_bins.append({
                'bin_id': bin_obj.bin_id,
                'lat': float(bin_obj.latitude),
                'lng': float(bin_obj.longitude),
                'garbage_level': float(latest.garbage_level),
            })
    return Response(full_bins)


@api_view(['POST'])
def seed_data(request):
    from accounts.models import CustomUser, Household
    import random
    from datetime import timedelta
    from django.utils import timezone
    
    num_households = int(request.data.get('num_households', 100))
    num_bins_per_household = int(request.data.get('num_bins', 5))
    num_iot_records = int(request.data.get('num_iot_records', 10))
    
    users_created = 0
    bins_created = 0
    iot_records = 0
    
    admin_user, created = CustomUser.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@iyunga.waste',
            'user_type': 'admin',
            'is_staff': True,
            'is_superuser': True,
        }
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
        users_created += 1
    
    for s in range(1, 6):
        staff_user, created = CustomUser.objects.get_or_create(
            username=f'collector{s}',
            defaults={
                'email': f'collector{s}@iyunga.waste',
                'user_type': 'collector',
                'phone': f'+25570000000{s}',
                'address': f'Collector {s}, Iyunga',
            }
        )
        if created:
            staff_user.set_password('collector123')
            staff_user.save()
            users_created += 1
    
    staff_users = list(CustomUser.objects.filter(user_type='collector'))
    
    base_lat = -8.899
    base_lng = 33.454
    
    for i in range(1, num_households + 1):
        user, created = CustomUser.objects.get_or_create(
            username=f'household{i}',
            defaults={
                'email': f'household{i}@iyunga.waste',
                'user_type': 'household',
                'phone': f'+2557{i:07d}',
                'address': f'Household {i}, Iyunga',
            }
        )
        if created:
            user.set_password('household123')
            user.save()
            users_created += 1
        
        household, created = Household.objects.get_or_create(
            user=user,
            name=f'Household {i}',
            defaults={
                'address': f'Plot {i}, Iyunga, Mbeya',
                'latitude': base_lat + random.uniform(-0.02, 0.02),
                'longitude': base_lng + random.uniform(-0.02, 0.02),
                'contact_phone': f'+2557{i:07d}',
            }
        )
        
        lat = base_lat + random.uniform(-0.02, 0.02)
        lng = base_lng + random.uniform(-0.02, 0.02)
        
        for j in range(1, num_bins_per_household + 1):
            bin_id = f'BIN{i:04d}-{j}'
            bin_obj, created = SmartBin.objects.get_or_create(
                bin_id=bin_id,
                defaults={
                    'latitude': lat + random.uniform(-0.002, 0.002),
                    'longitude': lng + random.uniform(-0.002, 0.002),
                    'location_name': f'Location {i}-{j}, Iyunga',
                    'household': household,
                    'assigned_collector': random.choice(staff_users) if staff_users else None,
                }
            )
            if created:
                bins_created += 1
            
            for k in range(num_iot_records):
                garbage = random.uniform(0, 100)
                recyclable = random.uniform(0, 100)
                recyclable_weight = random.uniform(0, 50) if recyclable > 20 else 0
                
                IoTData.objects.create(
                    bin=bin_obj,
                    garbage_level=garbage,
                    recyclable_level=recyclable,
                    recyclable_weight=recyclable_weight,
                    latitude=bin_obj.latitude,
                    longitude=bin_obj.longitude,
                    timestamp=timezone.now() - timedelta(days=random.randint(0, 30)),
                )
                iot_records += 1
    
    return Response({
        'success': True,
        'users': users_created,
        'bins': bins_created,
        'iot_records': iot_records,
        'message': f'Seeded {users_created} users, {bins_created} bins, {iot_records} IoT records'
    })