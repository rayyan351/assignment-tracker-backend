from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import sqlite3
import time

COURSES = {
    "MTQ2Njg1": "Applied Calculus & Analytical Geometry",
    "MTQ2Njg2": "Digital Design",
    "MTQ2Njg3": "Digital Design Lab",
    "MTQ2Njg5": "Functional English",
    "MTQ2Njkw": "Object Oriented Programming",
    "MTQ2Njkx": "OOP Lab",
    "MTQ2Njky": "Probability & Statistics",
    "MTQ5OTU0": "Fahm-e-Quran–I",
    "MTQ5OTU1": "Pakistan Studies & Global Perspective"
}

def sync_user_assignments(user):
    """
    user = {
        id: int,
        enrollment: str,
        password: str,
        email: str
    }
    """

    print(f"🧠 Sync started for {user['enrollment']}")

    db = sqlite3.connect("tracker.db")
    cur = db.cursor()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # ---------- CMS LOGIN ----------
        page.goto("https://cms.bahria.edu.pk/", timeout=60000)
        page.wait_for_load_state("domcontentloaded")

        page.click("#BodyPH_hlStudent")
        page.wait_for_selector("#BodyPH_tbEnrollment", timeout=60000)

        page.fill("#BodyPH_tbEnrollment", user["enrollment"])
        page.fill("#BodyPH_tbPassword", user["password"])
        page.select_option("#BodyPH_ddlInstituteID", "2")
        page.select_option("#BodyPH_ddlSubUserType", "None")

        page.click("#BodyPH_btnLogin")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        print("✅ CMS login OK")

        # ---------- OPEN LMS ----------
        with page.expect_popup(timeout=60000) as popup:
            page.click("text=LMS")

        lms = popup.value
        lms.wait_for_load_state("domcontentloaded")
        lms.wait_for_load_state("networkidle")

        print("✅ LMS opened")

        # ---------- ASSIGNMENTS ----------
        lms.goto(
            "https://lms.bahria.edu.pk/Student/Assignments.php",
            timeout=60000
        )

        lms.wait_for_selector("#semesterId", timeout=60000)
        lms.wait_for_selector("#courseId", timeout=60000)

        soup = BeautifulSoup(lms.content(), "html.parser")
        semester = soup.select_one("#semesterId option")["value"]

        for cid, cname in COURSES.items():
            print(f"📘 {cname}")

            lms.select_option("#courseId", cid)
            lms.wait_for_timeout(2500)

            soup = BeautifulSoup(lms.content(), "html.parser")
            table = soup.find("table", class_="table")

            if not table:
                continue

            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) < 8:
                    continue

                no = cols[0].get_text(strip=True)
                title = cols[1].get_text(strip=True)
                deadline = cols[7].get_text(strip=True)

                cur.execute("""
                    INSERT OR IGNORE INTO assignments
                    (user_id, semester, course, assignment_no, title, deadline)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    user["id"],
                    semester,
                    cname,
                    no,
                    title,
                    deadline
                ))

                db.commit()

        browser.close()

    db.close()
    print(f"✅ Sync complete for {user['enrollment']}")
