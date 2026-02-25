import os
import time
import psycopg2
import psycopg2.extras
import threading
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv
import requests
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

# -------------------- CONFIG --------------------
JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "THIS-KEY-MUST-BE-AT-LEAST-32-CHARS-LONG-123456"
)
JWT_EXP_HOURS = 24

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")

# -------------------- PLAYWRIGHT BROWSER POOL --------------------

playwright_instance = None
browser_instance = None
browser_lock = threading.Lock()


def get_browser():
    global playwright_instance, browser_instance

    with browser_lock:
        if browser_instance is None:
            logger.info("🌐 Launching persistent Playwright browser")

            playwright_instance = sync_playwright().start()

            browser_instance = playwright_instance.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process"
                ]
            )

        return browser_instance


# -------------------- APP --------------------
app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.route("/", methods=["GET"])
def root():
    return {"status": "API running successfully!"}

# -------------------- DATABASE --------------------
def init_db():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id SERIAL PRIMARY KEY,
      enrollment TEXT UNIQUE,
      password TEXT,
      email TEXT
    );

    CREATE TABLE IF NOT EXISTS assignments (
      id SERIAL PRIMARY KEY,
      user_id INTEGER,
      course TEXT,
      assignment_no TEXT,
      title TEXT,
      deadline TEXT,
      submitted INTEGER DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id, course, assignment_no)
    );

    CREATE TABLE IF NOT EXISTS sync_status (
      user_id INTEGER PRIMARY KEY,
      last_sync TEXT,
      syncing INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS email_logs (
      user_id INTEGER,
      assignment_key TEXT,
      type TEXT,
      sent_at TEXT,
      UNIQUE(user_id, assignment_key, type)
    );

    CREATE TABLE IF NOT EXISTS attendance (
     id SERIAL PRIMARY KEY,
     user_id INTEGER,
     course TEXT,
     present_hours REAL,
     total_hours REAL,
     last_checked TEXT,
     UNIQUE(user_id, course)
    );

    CREATE TABLE IF NOT EXISTS attendance_logs (
    user_id INTEGER,
    course TEXT,
    total_hours REAL,
    type TEXT,
    sent_at TEXT,
    UNIQUE(user_id, course, total_hours, type)
    );

    CREATE TABLE IF NOT EXISTS reminder_logs (
    user_id INTEGER,
    assignment_key TEXT,
    type TEXT,
    sent_at TEXT,
    UNIQUE(user_id, assignment_key, type)
    );
    """)
    conn.commit()
    conn.close()


def get_db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


init_db()

# -------------------- AUTH --------------------
def create_token(user_id):
    return jwt.encode(
        {
            "id": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        if request.method == "OPTIONS":
            return "", 200

        token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not token:
            return jsonify({"success": False}), 401

        try:

            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("SELECT * FROM users WHERE id=%s", (data["id"],))
            user = cur.fetchone()
            db.close()

            if not user:
                raise Exception("User not found")

            g.user = dict(user)

        except Exception as e:
            logger.error(f"JWT ERROR: {e}")
            return jsonify({"success": False}), 401

        return f(*args, **kwargs)

    return decorated


# -------------------- REGISTER --------------------
@app.route("/api/register", methods=["POST", "OPTIONS"])
def register():

    if request.method == "OPTIONS":
        return "", 200

    data = request.json

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:

        hashed = generate_password_hash(data["password"])

        cur.execute(
            "INSERT INTO users (enrollment, password, email) VALUES (%s, %s, %s)",
            (data["enrollment"], hashed, data["email"]),
        )

        db.commit()
        db.close()

        return jsonify({"success": True})

    except psycopg2.IntegrityError:

        db.close()

        return jsonify({"success": False, "message": "User exists"}), 400


# -------------------- LOGIN --------------------
@app.route("/api/login", methods=["POST", "OPTIONS"])
def login():

    if request.method == "OPTIONS":
        return "", 200

    data = request.json

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM users WHERE enrollment=%s",
        (data["enrollment"],),
    )

    user = cur.fetchone()

    db.close()

    if not user:
        return jsonify({"success": False}), 401

    if not check_password_hash(user["password"], data["password"]):
        return jsonify({"success": False}), 401

    threading.Thread(
        target=sync_user_assignments,
        args=(dict(user),),
        daemon=True
    ).start()

    return jsonify({
        "success": True,
        "token": create_token(user["id"])
    })


# -------------------- EMAIL --------------------
def send_email(to, subject, body):

    try:

        logger.info(f"📧 Sending email to {to}")

        url = "https://api.brevo.com/v3/smtp/email"

        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }

        payload = {
            "sender": {"email": EMAIL_FROM, "name": "Assignment Tracker"},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": body
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 201:
            logger.info("✅ Email sent successfully")
        else:
            logger.error(f"❌ Brevo error: {response.text}")

    except Exception as e:
        logger.error(f"❌ EMAIL ERROR: {e}")


# -------------------- LMS SYNC --------------------
def sync_user_assignments(user):

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:

        logger.info(f"🔄 Syncing LMS for {user['enrollment']}")

        browser = get_browser()

        page = browser.new_page()

        page.goto("https://cms.bahria.edu.pk/", timeout=60000)

        page.click("#BodyPH_hlStudent")
        page.fill("#BodyPH_tbEnrollment", user["enrollment"])
        page.fill("#BodyPH_tbPassword", user["password"])

        page.select_option("#BodyPH_ddlInstituteID", "2")
        page.select_option("#BodyPH_ddlSubUserType", "None")

        page.click("#BodyPH_btnLogin")

        page.wait_for_load_state("networkidle")

        if "Login.aspx" in page.url:
            raise Exception("Login failed")

        page.wait_for_selector("text=LMS", timeout=60000)

        with page.expect_popup() as pop:
            page.click("text=LMS")

        lms = pop.value

        lms.goto("https://lms.bahria.edu.pk/Student/Assignments.php")

        lms.wait_for_selector("#courseId", timeout=60000)

        soup = BeautifulSoup(lms.content(), "html.parser")

        options = [o["value"] for o in soup.select("#courseId option")]

        COURSES = {
            "MTQ2Njg1": "Applied Calculus & Analytical Geometry",
            "MTQ2Njg2": "Digital Design",
            "MTQ2Njg5": "Functional English",
            "MTQ2Njkw": "Object Oriented Programming",
            "MTQ2Njkx": "OOP Lab",
            "MTQ2Njky": "Probability & Statistics",
            "MTQ5OTU0": "Fahm-e-Quran–I",
            "MTQ5OTU1": "Pakistan Studies & Global Perspective",
            "MTUwMDA4": "Digital Design Lab",
        }

        for cid, cname in COURSES.items():

            if cid not in options:
                continue

            lms.select_option("#courseId", cid)

            time.sleep(2)

            soup = BeautifulSoup(lms.content(), "html.parser")

            table = soup.find("table", class_="table")

            if not table:
                continue

            for r in table.find_all("tr")[1:]:

                cols = r.find_all("td")

                if len(cols) < 8:
                    continue

                no = cols[0].text.strip()

                title = cols[1].text.strip()

                submission_cell = cols[3]

                submitted = 1 if submission_cell.find("a") else 0

                raw_deadline = cols[7].get_text(" ", strip=True)

                deadline = None

                if raw_deadline:

                    cleaned = re.sub(r"\s*-\s*", " - ", raw_deadline)

                    match = re.search(
                        r"\d{1,2}\s+[A-Za-z]+\s+\d{4}\s-\s\d{1,2}:\d{2}\s?(am|pm)",
                        cleaned,
                        re.IGNORECASE
                    )

                    if match:

                        deadline_obj = datetime.strptime(
                            match.group(0),
                            "%d %B %Y - %I:%M %p"
                        )

                        deadline = deadline_obj.replace(
                            tzinfo=timezone.utc
                        ).isoformat()

        page.close()

        conn.close()

        logger.info("✅ Sync finished")

    except Exception as e:

        logger.error(f"❌ SYNC ERROR: {e}")

        conn.close()


# -------------------- AUTO SYNC --------------------
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()


def auto_sync_all_users():

    logger.info("🔁 Auto sync scheduler triggered")

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM users")

    users = cur.fetchall()

    conn.close()

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as executor:

        for u in users:
            executor.submit(sync_user_assignments, dict(u))


scheduler.add_job(auto_sync_all_users, "interval", minutes=10)

# Prevent duplicate schedulers when using Gunicorn
if os.environ.get("RUN_MAIN") == "true" or not os.environ.get("WERKZEUG_RUN_MAIN"):
    scheduler.start()


# -------------------- SERVER --------------------
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    logger.info(f"🚀 Starting server on port {port}")

    app.run(host="0.0.0.0", port=port)