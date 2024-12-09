import sqlite3
import shutil
import time


def start_cleaner():
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS data(expires_at int, path text)")
    conn.commit()
    try:
        while True:
            now = time.time()
            cur.execute("SELECT path FROM data WHERE expires_at < ?", (now,))
            rows = cur.fetchall()
            for row in rows:
                path = row[0]
                try:
                    shutil.rmtree(path)
                    print(f"Deleted content at: {path}")
                except FileNotFoundError:
                    print(f"Directory not found: {path}")
                cur.execute("DELETE FROM data WHERE path = ?", (path,))
            conn.commit()
            time.sleep(10)  # Sleep for 30 minutes
    except KeyboardInterrupt:
        conn.commit()
        cur.close()
        conn.close()


if __name__ == "__main__":
    start_cleaner()
