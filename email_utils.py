import os
import requests

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_NAME = os.getenv("FROM_NAME", "Bahria LMS Tracker")

def send_email(to_email, subject, html):
    if not BREVO_API_KEY:
        print("⚠️ No Brevo API key set")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "sender": {"email": FROM_EMAIL, "name": FROM_NAME},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html
    }

    res = requests.post(url, json=data, headers=headers)
    if res.status_code not in (200, 201):
        print("❌ Email failed:", res.text)
    else:
        print("📧 Email sent →", to_email)


def new_assignment_html(course, title, deadline):
    return f"""
    <h2>🆕 New Assignment Posted</h2>
    <p><b>{course}</b></p>
    <p>{title}</p>
    <p><b>Deadline:</b> {deadline or "No deadline"}</p>
    """

def due_soon_html(course, title, deadline):
    return f"""
    <h2>⏰ Assignment Due Soon</h2>
    <p><b>{course}</b></p>
    <p>{title}</p>
    <p><b>Deadline:</b> {deadline}</p>
    """

def overdue_html(course, title):
    return f"""
    <h2>❌ Assignment Overdue</h2>
    <p><b>{course}</b></p>
    <p>{title}</p>
    """
