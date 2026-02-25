import sqlite3
import time
import threading
import logging
from main import sync_user_assignments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

AUTO_SYNC_INTERVAL = 600  # 10 minutes

def run_sync_cycle():

    conn = sqlite3.connect("assignments.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    users = cur.execute("SELECT * FROM users").fetchall()
    conn.close()

    logging.info(f"🔁 Syncing {len(users)} users")

    for user in users:
        threading.Thread(
            target=sync_user_assignments,
            args=(dict(user),),
            daemon=True
        ).start()


def worker_loop():

    logging.info("🚀 Worker started")

    while True:

        try:
            run_sync_cycle()

        except Exception as e:
            logging.error(f"Worker error: {e}")

        logging.info("⏳ Waiting for next cycle...")
        time.sleep(AUTO_SYNC_INTERVAL)


if __name__ == "__main__":
    worker_loop()