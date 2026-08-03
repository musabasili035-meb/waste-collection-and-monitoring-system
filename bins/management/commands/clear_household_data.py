from django.core.management.base import BaseCommand
from django.db import connection
from accounts.models import CustomUser, Household
from bins.models import SmartBin, IoTData
from payments.models import Payment, Receipt
from reports.models import Notification, CollectionRoute, CollectionSchedule


class Command(BaseCommand):
    help = 'Clear all household users, bins, IoT data, payments, schedules, routes, and notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-admin',
            action='store_true',
            help='Keep admin and collector users',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        keep_admin = options['keep_admin']
        confirm = options['confirm']

        if not confirm:
            self.stdout.write(self.style.WARNING(
                'This will DELETE all household data including:\n'
                '  - Household users\n'
                '  - Household profiles\n'
                '  - Smart bins\n'
                '  - IoT sensor data\n'
                '  - Payments & receipts\n'
                '  - Collection schedules & routes\n'
                '  - Notifications\n'
            ))
            answer = input('Type "YES" to confirm: ')
            if answer != 'YES':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        self.stdout.write('Clearing data...')

        n_notifications = Notification.objects.all().count()
        Notification.objects.all().delete()
        self.stdout.write(f'  Deleted {n_notifications} notifications')

        n_routes_bins = 0
        for route in CollectionRoute.objects.all():
            n_routes_bins += route.bins.count()
            route.bins.clear()
        n_routes = CollectionRoute.objects.all().count()
        CollectionRoute.objects.all().delete()
        self.stdout.write(f'  Deleted {n_routes} collection routes ({n_routes_bins} bin-route links)')

        n_schedules = CollectionSchedule.objects.all().count()
        CollectionSchedule.objects.all().delete()
        self.stdout.write(f'  Deleted {n_schedules} collection schedules')

        n_receipts = Receipt.objects.all().count()
        Receipt.objects.all().delete()
        self.stdout.write(f'  Deleted {n_receipts} receipts')

        n_payments = Payment.objects.all().count()
        Payment.objects.all().delete()
        self.stdout.write(f'  Deleted {n_payments} payments')

        n_iot = IoTData.objects.all().count()
        IoTData.objects.all().delete()
        self.stdout.write(f'  Deleted {n_iot} IoT data records')

        n_bins = SmartBin.objects.all().count()
        SmartBin.objects.all().delete()
        self.stdout.write(f'  Deleted {n_bins} smart bins')

        n_households = Household.objects.all().count()
        Household.objects.all().delete()
        self.stdout.write(f'  Deleted {n_households} household profiles')

        if keep_admin:
            deleted_users = CustomUser.objects.filter(user_type='household').count()
            CustomUser.objects.filter(user_type='household').delete()
            self.stdout.write(f'  Deleted {deleted_users} household users (kept admin/collectors)')
        else:
            deleted_users = CustomUser.objects.count()
            admin_count = CustomUser.objects.filter(user_type='admin').count()
            collector_count = CustomUser.objects.filter(user_type='collector').count()
            CustomUser.objects.filter(user_type='household').delete()
            self.stdout.write(f'  Deleted {deleted_users - admin_count - collector_count} household users (kept {admin_count} admins and {collector_count} collectors)')

        self.stdout.write(self.style.SUCCESS(
            '\nDone! Database cleared.\n'
            'The system is now ready to accept fresh ESP32 data.\n'
            'Register new bins and households before sending IoT data.'
        ))
