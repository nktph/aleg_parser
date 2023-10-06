from peewee import *
from playhouse.sqliteq import SqliteQueueDatabase

db = SqliteQueueDatabase('database.sqlite3')


class Ad(Model):
    id = IntegerField(primary_key=True, unique=True)
    link = CharField(unique=True)

    class Meta:
        db_table = 'Ads'
        database = db


def connect():
    print('conn')
    db.connect()
    db.create_tables([Ad])
