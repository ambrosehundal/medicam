purge_old_messages: python manage.py purge_old_messages
release: python manage.py migrate && python manage.py sync_languages
web: gunicorn medicam.wsgi
