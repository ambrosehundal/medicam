"""
Delete chat messages that are too old.
"""

from datetime import timedelta, datetime

from clinic.models import ChatMessage
from django.core.management.base import BaseCommand


MAX_AGE = timedelta(1)  # 1 day

class Command(BaseCommand):
	def handle(self, *args, **kwargs):
		old_messages = ChatMessage.objects.filter(
			sent__lte=datetime.now() - MAX_AGE
		).all()
		delete_count = old_messages.count()
		old_messages.delete()
		self.stdout.write(self.style.SUCCESS(f"Deleted {delete_count} messages."))
