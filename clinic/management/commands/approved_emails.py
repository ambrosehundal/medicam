from clinic.models import Doctor
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
	def handle(self, *args, **kwargs):
		doctors = Doctor.objects.filter(verified=True, email__isnull=False).exclude(email='')
		rows = [','.join((d.name, d.email)) for d in doctors]
		print('\n'.join(rows))
