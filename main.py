import os
import time
import sqlite3
import threading
import jwt
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv

load_dotenv()

# -------------------- CONFIG --------------------
JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "THIS-KEY-MUST-BE-AT-LEAST-32-CHARS-LONG-123456"
)
JWT_EXP_HOURS = 24
AUTO_SYNC_INTERVAL = 600

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM")

# -------------------- APP --------------------
app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.route("/", methods=["GET"])
def root():
    return {"status": "API running successfully!"}

# -------------------- DATABASE --------------------
def init_db():
    conn = sqlite3.connect("assignments.db")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      enrollment TEXT UNIQUE,
      password TEXT,
      email TEXT
    );

    CREATE TABLE IF NOT EXISTS assignments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      course TEXT,
      assignment_no TEXT,
      title TEXT,
      deadline TEXT,
      submitted INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
     id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn = sqlite3.connect("assignments.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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
            user = db.execute(
                "SELECT * FROM users WHERE id=?",
                (data["id"],)
            ).fetchone()
            db.close()

            if not user:
                raise Exception("User not found")

            g.user = dict(user)

        except Exception as e:
            print("JWT ERROR:", e)
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

    try:
     

        db.execute(
            "INSERT INTO users (enrollment, password, email) VALUES (?, ?, ?)",
            (data["enrollment"], data["password"], data["email"]),
        )
        db.commit()
        db.close()

        return jsonify({"success": True})

    except sqlite3.IntegrityError:
        db.close()
        return jsonify({"success": False, "message": "User exists"}), 400


# -------------------- LOGIN --------------------
@app.route("/api/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return "", 200

    data = request.json
    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE enrollment=?",
        (data["enrollment"],),
    ).fetchone()

    db.close()

    if not user:
        return jsonify({"success": False}), 401

    # 🔐 Verify hashed password
    if data["password"] != user["password"]:
        return jsonify({"success": False}), 401


    # Auto sync on login
    threading.Thread(
        target=sync_user_assignments,
        args=(dict(user),),
        daemon=True
    ).start()

    return jsonify({
        "success": True,
        "token": create_token(user["id"])
    })


def format_deadline_12hr(iso_string):
    if not iso_string:
        return "No deadline"

    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%d %B %Y - %I:%M %p")
    except:
        return iso_string


def check_24hr_deadlines(user):
    conn = sqlite3.connect("assignments.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    now = datetime.now(timezone.utc)
    next_24 = now + timedelta(hours=24)

    rows = cur.execute("""
        SELECT * FROM assignments
        WHERE user_id=? AND submitted=0 AND deadline IS NOT NULL
    """, (user["id"],)).fetchall()

    for r in rows:
        if r["deadline"]:
          deadline = datetime.fromisoformat(r["deadline"]).replace(tzinfo=timezone.utc)


        if now < deadline <= next_24:
            key = f"{r['course']}-{r['assignment_no']}"

            exists = cur.execute("""
                SELECT 1 FROM reminder_logs
                WHERE user_id=? AND assignment_key=? AND type='24hr'
            """, (user["id"], key)).fetchone()

            if exists:
                continue

            formatted_deadline = format_deadline_12hr(r["deadline"])

            send_email(
                user["email"],
                f"⏰ 24 Hour Reminder — {r['course']}",
                f"""
                <h3>{r['course']}</h3>
                <p><b>{r['title']}</b></p>
                <p>Deadline: <b>{formatted_deadline}</b></p>
                <p>This assignment is due within 24 hours!</p>
                """
            )

            cur.execute("""
                INSERT INTO reminder_logs VALUES (?, ?, '24hr', ?)
            """, (
                user["id"],
                key,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    conn.close()

# -------------------- SYNC STATUS --------------------
@app.route("/api/sync/status")
@jwt_required
def sync_status():
    db = get_db()
    row = db.execute(
        "SELECT last_sync, syncing FROM sync_status WHERE user_id=?",
        (g.user["id"],),
    ).fetchone()
    db.close()

    return jsonify({
        "syncing": bool(row["syncing"]) if row else False,
        "lastSync": row["last_sync"] if row else None
    })


# -------------------- ASSIGNMENTS --------------------
@app.route("/api/assignments", methods=["GET", "OPTIONS"])
@jwt_required
def get_assignments():
    if request.method == "OPTIONS":
        return "", 200

    db = get_db()

    rows = db.execute(
        """
        SELECT course, assignment_no, title, deadline, submitted, created_at
        FROM assignments
        WHERE user_id=?
        ORDER BY deadline ASC
        """,
        (g.user["id"],),
    ).fetchall()



    db.close()

    return jsonify({
        "success": True,
        "count": len(rows),
        "assignments": [
            {
                "course": r["course"],
                "no": r["assignment_no"],
                "title": r["title"],
                "deadline": r["deadline"],
                "submitted": bool(r["submitted"]),
                "createdAt": r["created_at"],
            }
            for r in rows
        ]
    })

# -------------------- ATTENDANCE --------------------
@app.route("/api/attendance", methods=["GET", "OPTIONS"])
@jwt_required
def get_attendance():
    if request.method == "OPTIONS":
        return "", 200

    db = get_db()
    cur = db.cursor()

    rows = cur.execute("""
        SELECT course, present_hours, total_hours, last_checked
        FROM attendance
        WHERE user_id=?
        ORDER BY course ASC
    """, (g.user["id"],)).fetchall()

    attendance_data = []

    for r in rows:
        course_name = r["course"]
        present_hours = r["present_hours"] or 0
        total_hours = r["total_hours"] or 0

        percentage = 0
        if total_hours > 0:
            percentage = round((present_hours / total_hours) * 100, 2)

        # -------- LOW ATTENDANCE LOGIC --------
        if percentage < 75:

            exists = cur.execute("""
                SELECT 1 FROM attendance_logs
                WHERE user_id=? AND course=? AND total_hours=? AND type='low'
            """, (
                g.user["id"],
                course_name,
                total_hours
            )).fetchone()

            if not exists:

                send_email(
                    g.user["email"],
                    f"⚠ Low Attendance Warning — {course_name}",
                    f"""
                    <h3>{course_name}</h3>
                    <p>Your attendance dropped below 75%.</p>
                    <p>Present: {present_hours}</p>
                    <p>Total: {total_hours}</p>
                    <p>Percentage: <b>{percentage}%</b></p>
                    """
                )

                cur.execute("""
                    INSERT INTO attendance_logs
                    (user_id, course, total_hours, type, sent_at)
                    VALUES (?, ?, ?, 'low', ?)
                """, (
                    g.user["id"],
                    course_name,
                    total_hours,
                    datetime.now(timezone.utc).isoformat()
                ))

                db.commit()

        attendance_data.append({
            "course": course_name,
            "present": present_hours,
            "total": total_hours,
            "percentage": percentage,
            "lastChecked": r["last_checked"]
        })

    db.close()

    return jsonify({
        "success": True,
        "attendance": attendance_data
    })


def send_weekly_summary(user):
    conn = sqlite3.connect("assignments.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    assignments = cur.execute("""
        SELECT * FROM assignments
        WHERE user_id=? AND submitted=0
        ORDER BY deadline ASC
    """, (user["id"],)).fetchall()

    attendance = cur.execute("""
        SELECT * FROM attendance
        WHERE user_id=?
    """, (user["id"],)).fetchall()

    assignment_html = ""
    for a in assignments:
        formatted_deadline = format_deadline_12hr(a["deadline"])
        assignment_html += f"""
        <li>
            <b>{a['course']}</b> - {a['title']}<br>
            Deadline: {formatted_deadline}
        </li>
        """

    attendance_html = ""
    for at in attendance:
        percent = 0
        if at["total_hours"] > 0:
            percent = round((at["present_hours"]/at["total_hours"])*100,2)

        attendance_html += f"""
        <li>
            <b>{at['course']}</b> - {percent}%
        </li>
        """

    send_email(
        user["email"],
        "📊 Weekly Academic Summary",
        f"""
        <h2>Your Weekly Summary</h2>
        <h3>Pending Assignments</h3>
        <ul>{assignment_html}</ul>

        <h3>Attendance</h3>
        <ul>{attendance_html}</ul>
        """
    )

    conn.close()


# -------------------- EMAIL --------------------
def send_email(to, subject, body):
    try:
        print(f"📧 Sending email to {to}")

        msg = MIMEText(body, "html")
        msg["From"] = EMAIL_FROM
        msg["To"] = to
        msg["Subject"] = subject

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        print("✅ Email sent successfully")

    except Exception as e:
        print("❌ EMAIL ERROR:", e)



def send_assignment_alert(db, user, assignment):
    key = f"{assignment['course']}-{assignment['assignment_no']}"

    exists = db.execute(
        "SELECT 1 FROM email_logs WHERE user_id=? AND assignment_key=? AND type='new'",
        (user["id"], key),
    ).fetchone()

    if exists:
        return

    try:
        send_email(
            user["email"],
            "📢 New Assignment Uploaded",
            f"""
            <h3>{assignment['course']}</h3>
            <p><b>{assignment['title']}</b></p>
            <p>Deadline: {assignment['deadline']}</p>
            """
        )

        db.execute(
            "INSERT INTO email_logs VALUES (?, ?, 'new', ?)",
            (user["id"], key, datetime.now(timezone.utc).isoformat()),
        )
        db.commit()

        print("📨 Email log saved")

    except Exception as e:
        print("❌ Failed to send assignment alert:", e)



# -------------------- LMS SYNC --------------------
def sync_user_assignments(user):
    conn = sqlite3.connect("assignments.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # ---------------- CHECK IF ALREADY SYNCING ----------------
        existing = cur.execute(
            "SELECT syncing FROM sync_status WHERE user_id=?",
            (user["id"],)
        ).fetchone()

        if existing and existing["syncing"] == 1:
            print("⚠ Already syncing, skipping...")
            return

        # Mark as syncing
        cur.execute(
            "INSERT OR REPLACE INTO sync_status (user_id, last_sync, syncing) VALUES (?, ?, 1)",
            (user["id"], datetime.now(timezone.utc).isoformat())
        )
        conn.commit()

        print("🔄 Syncing LMS for", user["enrollment"])

        # ---------------- PLAYWRIGHT LOGIN ----------------
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
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
                raise Exception("Login failed for user: " + user["enrollment"])

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

                    # ---------------- CHECK SUBMISSION COLUMN ----------------
                    submission_cell = cols[3]
                    submitted = 1 if submission_cell.find("a") else 0

                    # ---------------- DEADLINE PARSING ----------------
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
                            try:
                                deadline_obj = datetime.strptime(
                                    match.group(0),
                                    "%d %B %Y - %I:%M %p"
                                )
                                deadline = deadline_obj.isoformat()
                            except Exception as parse_error:
                                print("❌ Date parse failed:", match.group(0))
        
                    # ---------------- SAVE TO DATABASE ----------------
                    key = f"{cname}-{no}"

                    existing_assignment = cur.execute(
                        "SELECT id FROM assignments WHERE user_id=? AND course=? AND assignment_no=?",
                        (user["id"], cname, no)
                    ).fetchone()

                    is_new = existing_assignment is None

                    cur.execute("""
                        INSERT INTO assignments
                        (user_id, course, assignment_no, title, deadline, submitted)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, course, assignment_no)
                        DO UPDATE SET
                            deadline=excluded.deadline,
                            submitted=excluded.submitted
                    """,
                    (user["id"], cname, no, title, deadline, submitted)
                    )
                    if is_new:
                       print("🆕 New assignment detected:", cname, no)

                    # 🔥 SEND EMAIL ONLY IF NEW
                    if is_new:
                        send_assignment_alert(conn, user, {
                            "course": cname,
                            "assignment_no": no,
                            "title": title,
                            "deadline": deadline
                        })

            # ---------------- ATTENDANCE SYNC ----------------
            print("📊 Checking attendance...")

            # ✅ USE SAME PAGE (already logged into CMS)
            page.goto(
                "https://cms.bahria.edu.pk/Sys/Student/ClassAttendance/StudentWiseAttendance.aspx",
                timeout=60000
            )

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            html = page.content()

            DEBUG_PATH = os.path.join(os.getcwd(), "attendance_debug.html")
            print("🧪 Writing debug HTML to:", DEBUG_PATH)

            with open(DEBUG_PATH, "w", encoding="utf-8") as f:
                f.write(html)

            soup = BeautifulSoup(html, "html.parser")

            table = soup.find("table")


            if not table:
                print("❌ Attendance table NOT found")
            else:
                print("✅ Attendance table found")

                rows = table.find_all("tr")[1:]

                for r in rows:
                    cols = r.find_all("td")
                    if len(cols) < 12:
                        continue

                    course_name = cols[2].text.strip()

                    # Present hours example: "9.0 :100%"
                    present_text = cols[9].text.strip()
                    present_hours = float(present_text.split(":")[0])

                    total_hours = float(cols[11].text.strip())

                    existing = cur.execute(
                        "SELECT present_hours, total_hours FROM attendance WHERE user_id=? AND course=?",
                        (user["id"], course_name)
                    ).fetchone()

                    if not existing:
                        # First time snapshot
                        cur.execute("""
                            INSERT INTO attendance
                            (user_id, course, present_hours, total_hours, last_checked)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            user["id"],
                            course_name,
                            present_hours,
                            total_hours,
                            datetime.now(timezone.utc).isoformat()
                        ))
                        conn.commit()
                        continue

                    old_present = existing["present_hours"]
                    old_total = existing["total_hours"]

                    # New class happened
                    if total_hours > old_total:

                        if present_hours > old_present:
                            status = "present"
                        else:
                            status = "absent"

                        send_attendance_alert(
                            user,
                            course_name,
                            status,
                            present_hours,
                            total_hours
                        )

                    # Update snapshot
                    cur.execute("""
                        UPDATE attendance
                        SET present_hours=?, total_hours=?, last_checked=?
                        WHERE user_id=? AND course=?
                    """, (
                        present_hours,
                        total_hours,
                        datetime.now(timezone.utc).isoformat(),
                        user["id"],
                        course_name
                    ))
                    conn.commit()


            print("✅ Attendance sync complete")            

            browser.close()

        # ---------------- MARK SYNC COMPLETE ----------------
        cur.execute(
            "UPDATE sync_status SET syncing=0, last_sync=? WHERE user_id=?",
            (datetime.now(timezone.utc).isoformat(), user["id"])
        )
        conn.commit()

        print("✅ Sync done for", user["enrollment"])

        check_24hr_deadlines(user)
        if datetime.now().weekday() == 6:  # Sunday
         send_weekly_summary(user)

    except Exception as e:
        print("❌ SYNC ERROR:", e)

        # 🔥 CRITICAL: ALWAYS RESET SYNC FLAG ON ERROR
        cur.execute(
            "UPDATE sync_status SET syncing=0 WHERE user_id=?",
            (user["id"],)
        )
        conn.commit()

    finally:
        conn.close()

def send_attendance_alert(user, course, status, present, total):
    try:
        if status == "present":
            subject = f"✅ Attendance Marked — {course}"
            body = f"""
            <h3>{course}</h3>
            <p>Your attendance was marked <b>PRESENT</b>.</p>
            <p>Total Classes: {total}</p>
            <p>Present: {present}</p>
            """
        else:
            subject = f"⚠ Attendance Marked ABSENT — {course}"
            body = f"""
            <h3>{course}</h3>
            <p>You were marked <b>ABSENT</b>.</p>
            <p>If this is incorrect, verify with your teacher immediately.</p>
            <p>Total Classes: {total}</p>
            <p>Present: {present}</p>
            """

        send_email(user["email"], subject, body)

    except Exception as e:
        print("❌ Attendance email error:", e)


@app.route("/api/sync", methods=["POST"])
@jwt_required
def manual_sync():
    threading.Thread(
        target=sync_user_assignments,
        args=(g.user,),
        daemon=True
    ).start()

    return jsonify({"success": True})


# -------------------- AUTO SYNC --------------------
def auto_sync_loop():
    while True:
        print("⏳ Waiting for next auto sync...")
        time.sleep(AUTO_SYNC_INTERVAL)

        print("🔁 Running auto sync...")

        conn = sqlite3.connect("assignments.db")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        users = cur.execute("SELECT * FROM users").fetchall()
        conn.close()

        for u in users:
            sync_user_assignments(dict(u))
# -------------------- START --------------------
if __name__ == "__main__":
        # Render sets PORT automatically
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Starting server on port {port}")
    app.run(host="0.0.0.0", port=port)
