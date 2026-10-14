"""SQLite setup and clearly labelled fictional sample data for JeevanSetu AI."""

from datetime import datetime, timedelta
from pathlib import Path
import sqlite3


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def get_db(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(database_path: str | Path, schema_path: str | Path) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with get_db(database_path) as db:
        db.executescript(Path(schema_path).read_text(encoding="utf-8"))
        patient_profile_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(patient_profiles)")
        }
        patient_profile_migrations = {
            "care_category": "TEXT NOT NULL DEFAULT ''",
            "care_information": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in patient_profile_migrations.items():
            if column not in patient_profile_columns:
                db.execute(
                    f"ALTER TABLE patient_profiles ADD COLUMN {column} {definition}"
                )
        otp_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(patient_otp_challenges)")
        }
        if "consumed_at" not in otp_columns:
            db.execute("ALTER TABLE patient_otp_challenges ADD COLUMN consumed_at TEXT")
        otp_migrations = {
            "provider": "TEXT NOT NULL DEFAULT 'demo'",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
        }
        for column, definition in otp_migrations.items():
            if column not in otp_columns:
                db.execute(
                    f"ALTER TABLE patient_otp_challenges ADD COLUMN {column} {definition}"
                )
        directory_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(healthcare_directory)")
        }
        directory_migrations = {
            "facility_id": "TEXT",
            "ownership_type": (
                "TEXT NOT NULL DEFAULT 'unknown' "
                "CHECK (ownership_type IN ('government', 'private', 'unknown'))"
            ),
            "services": "TEXT NOT NULL DEFAULT ''",
            "latitude": "REAL",
            "longitude": "REAL",
            "blood_stock": "TEXT NOT NULL DEFAULT ''",
            "opening_hours": "TEXT NOT NULL DEFAULT ''",
            "last_checked": "TEXT",
            "notes": "TEXT NOT NULL DEFAULT ''",
            "source_verification_status": "TEXT NOT NULL DEFAULT ''",
            "potentially_duplicate": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in directory_migrations.items():
            if column not in directory_columns:
                db.execute(
                    f"ALTER TABLE healthcare_directory ADD COLUMN {column} {definition}"
                )
        db.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS healthcare_directory_facility_id
               ON healthcare_directory(facility_id) WHERE facility_id IS NOT NULL"""
        )
        doctor_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(doctors)")
        }
        if "verified" not in doctor_columns:
            db.execute(
                "ALTER TABLE doctors ADD COLUMN verified INTEGER NOT NULL DEFAULT 0 "
                "CHECK (verified IN (0, 1))"
            )
        report_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(medical_reports)")
        }
        if "language" not in report_columns:
            db.execute(
                "ALTER TABLE medical_reports ADD COLUMN language TEXT NOT NULL DEFAULT 'en'"
            )
        blood_request_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(blood_requests)")
        }
        if "status" not in blood_request_columns:
            db.execute(
                """ALTER TABLE blood_requests ADD COLUMN status TEXT NOT NULL DEFAULT 'Open'
                   CHECK (status IN ('Open', 'Resolved', 'Cancelled'))"""
            )

        if not db.execute(
            """SELECT 1 FROM healthcare_directory
               WHERE name = ? AND category = ? AND city = ?""",
            ("National Cancer Institute Nagpur", "cancer", "Nagpur"),
        ).fetchone():
            db.execute(
                """INSERT INTO healthcare_directory
                   (name, category, city, specialty, source_url, verification_status)
                   VALUES (?, 'cancer', 'Nagpur', 'Cancer care / oncology', ?, 'unverified')""",
                (
                    "National Cancer Institute Nagpur",
                    "https://ncinagpur.in/",
                ),
            )

        legacy_booking_constraint = False
        for index in db.execute("PRAGMA index_list(appointments)"):
            if not index["unique"] or index["origin"] != "u":
                continue
            columns = [
                row["name"]
                for row in db.execute(f"PRAGMA index_info('{index['name']}')")
            ]
            if columns == ["patient_id", "slot_id"]:
                legacy_booking_constraint = True
                break
        if legacy_booking_constraint:
            db.execute("PRAGMA foreign_keys = OFF")
            try:
                db.execute("BEGIN")
                db.execute(
                    """CREATE TABLE appointments_rebuilt (
                        id INTEGER PRIMARY KEY,
                        patient_id INTEGER NOT NULL REFERENCES users(id),
                        doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                        slot_id INTEGER NOT NULL REFERENCES doctor_slots(id),
                        status TEXT NOT NULL DEFAULT 'Pending'
                            CHECK (status IN ('Pending', 'Confirmed', 'Cancelled', 'Completed')),
                        visit_reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )"""
                )
                db.execute(
                    """INSERT INTO appointments_rebuilt
                       (id, patient_id, doctor_id, slot_id, status, visit_reason, created_at)
                       SELECT id, patient_id, doctor_id, slot_id, status, visit_reason, created_at
                       FROM appointments"""
                )
                db.execute("DROP TABLE appointments")
                db.execute("ALTER TABLE appointments_rebuilt RENAME TO appointments")
                db.commit()
                db.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_slot
                       ON appointments(slot_id) WHERE status IN ('Pending', 'Confirmed')"""
                )
            except sqlite3.Error:
                db.rollback()
                raise
            finally:
                db.execute("PRAGMA foreign_keys = ON")

        hospitals = [
            ("Harborview Teaching Hospital (Fictional Demo)", "12 Example Road", "Pune", "Shivajinagar", "+91 20 5550 0101", "Demo hours: 9:00 AM-5:00 PM", "Oncology, Dialysis, Hematology", 18.5308, 73.8475),
            ("Sahyadri Community Centre (Fictional Demo)", "8 Sample Lane", "Pune", "Kothrud", "+91 20 5550 0102", "Demo hours: 8:00 AM-6:00 PM", "Nephrology, General Medicine", 18.5074, 73.8077),
            ("Jeevan City Care (Fictional Demo)", "4 Placeholder Avenue", "Mumbai", "Dadar", "+91 22 5550 0103", "Demo hours: 10:00 AM-4:00 PM", "Oncology, Blood Services", 19.0176, 72.8562),
        ]
        for hospital in hospitals:
            if not db.execute(
                "SELECT 1 FROM hospitals WHERE name = ? AND is_demo = 1",
                (hospital[0],),
            ).fetchone():
                db.execute(
                    """INSERT INTO hospitals
                       (name, address, city, area, phone, opening_hours, specialties,
                        latitude, longitude, verified, is_demo)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""",
                    hospital,
                )

        blood_banks = [
            ("Example City Blood Centre (Fictional Demo)", "2 Sample Road", "Pune", "+91 20 5550 0201", "Demo hours: 9:00 AM-4:00 PM"),
            ("Community Blood Desk (Fictional Demo)", "6 Placeholder Street", "Mumbai", "+91 22 5550 0202", "Demo hours: 10:00 AM-3:00 PM"),
        ]
        for bank in blood_banks:
            if not db.execute(
                "SELECT 1 FROM blood_banks WHERE name = ? AND is_demo = 1",
                (bank[0],),
            ).fetchone():
                db.execute(
                    """INSERT INTO blood_banks (name, address, city, phone, opening_hours, is_demo)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    bank,
                )

        hospital_rows = {
            row["name"]: row["id"]
            for row in db.execute("SELECT id, name FROM hospitals WHERE is_demo = 1")
        }
        doctors = [
            ("Dr. Asha Kulkarni (Fictional Demo)", "Medical Oncology", "Harborview Teaching Hospital (Fictional Demo)", 12, "In-person and video placeholder"),
            ("Dr. Rohan Mehta (Fictional Demo)", "Nephrology", "Sahyadri Community Centre (Fictional Demo)", 9, "In-person"),
            ("Dr. Mira Shah (Fictional Demo)", "Hematology", "Jeevan City Care (Fictional Demo)", 15, "In-person and video placeholder"),
        ]
        for name, specialty, hospital_name, experience, mode in doctors:
            if not db.execute(
                "SELECT 1 FROM doctors WHERE name = ? AND is_demo = 1",
                (name,),
            ).fetchone():
                db.execute(
                    """INSERT INTO doctors (name, specialty, hospital_id, experience_years, consultation_mode, is_demo)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (name, specialty, hospital_rows[hospital_name], experience, mode),
                )

        slot_times = ("10:00", "11:30", "14:00")
        slots = db.execute("SELECT id FROM doctors WHERE is_demo = 1").fetchall()
        today = datetime.now().date()
        future_dates = [
            (today + timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(1, 15)
            if (today + timedelta(days=offset)).weekday() < 5
        ]
        for doctor in slots:
            for date in future_dates:
                for slot_time in slot_times:
                    db.execute(
                        """INSERT OR IGNORE INTO doctor_slots (doctor_id, slot_at, is_demo)
                           VALUES (?, ?, 1)""",
                        (doctor["id"], f"{date}T{slot_time}"),
                    )

        if not db.execute(
            "SELECT 1 FROM blood_requests WHERE is_demo = 1 LIMIT 1"
        ).fetchone():
            db.execute(
                """INSERT INTO blood_requests
                   (user_id, blood_group, hospital_location, city, urgency, contact_name,
                    contact_phone, details, is_demo, status)
                   VALUES (NULL, 'O+', 'Jeevan City Care (Fictional Demo)', 'Mumbai',
                           'Urgent', 'Fictional demo contact', '+91 22 5550 0199',
                           'Fictional sample request. Contact details are not displayed.', 1, 'Open')"""
            )
