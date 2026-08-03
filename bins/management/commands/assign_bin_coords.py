from django.core.management.base import BaseCommand
from bins.models import SmartBin
import random


IYUNGA_CENTER_LAT = -8.899
IYUNGA_CENTER_LNG = 33.454


class Command(BaseCommand):
    help = 'Assign coordinates within Iyunga, Mbeya to bins that have zero coordinates'

    def handle(self, *args, **options):
        bins = SmartBin.objects.filter(latitude=0, longitude=0)
        count = bins.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No bins need coordinate assignment'))
            return

        for bin_obj in bins:
            bin_obj.latitude = IYUNGA_CENTER_LAT + random.uniform(-0.015, 0.015)
            bin_obj.longitude = IYUNGA_CENTER_LNG + random.uniform(-0.015, 0.015)
            bin_obj.save(update_fields=['latitude', 'longitude'])

        self.stdout.write(
            self.style.SUCCESS(f'Assigned Iyunga coordinates to {count} bin(s)')
        )
