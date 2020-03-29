# medicam - the software powering doc19.org

https://doc19.org is a COVID-19 telehealth clinic, built on Django and Twilio.

## Requirements

### System Requirements

- Python 3.7
- Postgres 11

You can use [asdf] to manage your environment versions.

## Running the App
First run a virtualenv using `virtualenv .venv && source .venv/bin/activate`

Install Python dependencies using `pip install -r requirements.txt`

Make sure that `DEBUG`, `SECRET_KEY`, `DATABASE_URL` and `SITE_ID` are set as environment variables.

The easiest way to run the app is utilizing [heroku-cli].

```
export DEBUG=1 SECRET_KEY=x SITE_ID=1 DATABASE_URL=sqlite:///db.sqlite3
heroku local release
heroku local web
```

If you get an error about missing staticfiles, try running:
`python manage.py collectstatic`

To access the Django admin run `python manage.py createsuperuser` and then go to `localhost:PORT/admin123/` where you should be prompted to login with the credentials you set.

## Resources
- Help With COVID project page: https://helpwithcovid.com/projects/147
- Discord invite link: https://discord.gg/CqeH4wA


[asdf]: https://github.com/asdf-vm/asdf
[heroku-cli]: https://devcenter.heroku.com/articles/heroku-cli#download-and-install
