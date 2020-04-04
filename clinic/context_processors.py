from django.conf import settings

def sentry_config(request):
	if settings.SENTRY_DSN:
		return {'SENTRY_CONFIG': {'dsn': settings.SENTRY_DSN}}
	else:
		return {}
