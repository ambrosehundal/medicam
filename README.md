# medicam - the software powering doc19.org

https://doc19.org is a COVID-19 telehealth clinic, built on Django and Twilio.

## Requirements

### System Requirements

- Python 3.7
- Postgres 11

You can use [asdf] to manage your environment versions.

## Running the App

The easiest way to run the app is utilizing [heroku-cli].

```
export DEBUG=1 SECRET_KEY=x SITE_ID=1 DATABASE_URL=sqlite:///db.sqlite3
heroku local release
heroku local web
```

## Resources
- Help With COVID project page: https://helpwithcovid.com/projects/147
- Discord invite link: https://discord.gg/CqeH4wA


[asdf]: https://github.com/asdf-vm/asdf
[heroku-cli]: https://devcenter.heroku.com/articles/heroku-cli#download-and-install
