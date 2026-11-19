from dotenv import load_dotenv
import os
import psycopg2

load_dotenv(override=True)

conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
cur = conn.cursor()

cur.execute("SELECT company_id, name FROM companies LIMIT 5;")
rows = cur.fetchall()

for row in rows:
    print(row)

cur.close()
conn.close()
