import sqlite3

conn = sqlite3.connect("db.sqlite3")
cur = conn.cursor()
cur.execute("DELETE FROM django_migrations WHERE app='finance' AND name LIKE '0009%'")
cur.execute("DELETE FROM django_migrations WHERE app='market' AND name LIKE '0018%'")
conn.commit()
conn.close()
print("Cleaned migration history for corrupted merges")
