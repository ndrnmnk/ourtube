import sqlite3
import logging
import shutil
import time
from utils.config import Config

class Cleaner:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path="data.db"):
        self.db_path = db_path
        self.sleep_time = Config().get("cleaner_interval", 300)

    def remove_content_at(self, content_path):
        try:
            shutil.rmtree(content_path)
            logging.info(f"Deleted content at {content_path}")
        except FileNotFoundError:
            logging.info(f"Directory not found: {content_path}")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM data WHERE path = ?", (content_path,))
            conn.commit()

    def add_content(self, content_path, expires_at):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO data (expires_at, path) VALUES (?, ?)", (expires_at, content_path))
            conn.commit()

    def run(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS data(expires_at int, path text)")
            conn.commit()

            try:
                while True:
                    now = time.time()
                    cur.execute("SELECT path FROM data WHERE expires_at < ?", (now,))
                    rows = cur.fetchall()
                    for row in rows:
                        self.remove_content_at(row[0])
                    time.sleep(self.sleep_time)
            except KeyboardInterrupt:
                logging.info("Cleaner interrupted. Exiting.")