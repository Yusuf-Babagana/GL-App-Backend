import sqlite3
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.execute("SELECT id, app, name, applied FROM django_migrations WHERE app='market' ORDER BY id")
rows = cursor.fetchall()
for r in rows:
    print(r)
conn.close()
