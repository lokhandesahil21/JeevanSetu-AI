import io
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai import OpenAIError
from PIL import Image
from requests import ConnectionError as RequestsConnectionError
from werkzeug.security import generate_password_hash

from app import create_app
from database import get_db, init_db


class JeevanSetuAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database_path = root / "test.sqlite3"
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE": str(self.database_path),
            "UPLOAD_FOLDER": str(root / "uploads"),
            "SMS_OTP_MODE": "demo",
        })
        self.client = self.app.test_client()
        self.registration_counter = 0

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf(self, client=None):
        client = client or self.client
        with client.session_transaction() as session:
            session.setdefault("csrf_token", "test-csrf-token")
            return session["csrf_token"]

    def csrf_headers(self, client=None):
        return {"X-CSRF-Token": self.csrf(client)}

    def register(self, email="patient@example.test", name="Test Patient"):
        self.registration_counter += 1
        mobile = f"+9198765432{self.registration_counter:02d}"
        self.client.get("/patient/register")
        response = self.client.post("/patient/register", data={
            "csrf_token": self.csrf(),
            "name": name,
            "email": email,
            "mobile": mobile,
            "age": "35",
            "area_city": "Nagpur",
            "care_category": "cancer",
            "privacy_consent": "yes",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        return response

    def verified_doctor_slots(self, count=2):
        with get_db(self.database_path) as db:
            hospital_id = db.execute(
                """INSERT INTO hospitals
                   (name, address, city, area, specialties, verified, is_demo)
                   VALUES (?, ?, ?, ?, ?, 1, 0)""",
                ("Verified Test Hospital", "1 Test Road", "Nagpur", "Civil Lines", "General Medicine"),
            ).lastrowid
            doctor_id = db.execute(
                """INSERT INTO doctors
                   (name, specialty, hospital_id, consultation_mode, is_demo, verified)
                   VALUES (?, ?, ?, ?, 0, 1)""",
                ("Verified Test Doctor", "General Medicine", hospital_id, "Video"),
            ).lastrowid
            slot_ids = []
            for offset in range(count):
                slot_at = (datetime.now() + timedelta(days=3 + offset)).strftime("%Y-%m-%dT10:00")
                slot_ids.append(db.execute(
                    """INSERT INTO doctor_slots (doctor_id, slot_at, is_demo)
                       VALUES (?, ?, 0)""",
                    (doctor_id, slot_at),
                ).lastrowid)
        return doctor_id, slot_ids

    @staticmethod
    def text_pdf(report_line):
        text = report_line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = (
            "BT\n/F1 12 Tf\n72 720 Td\n("
            + text
            + ") Tj\nET"
        ).encode("ascii")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
            + stream + b"\nendstream",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, body in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode("ascii"))
            pdf.extend(body + b"\nendobj\n")
        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010} 00000 n \n".encode("ascii"))
        pdf.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        return bytes(pdf)

    def test_demo_directory_and_search_are_available_without_login(self):
        response = self.client.get("/hospitals?city=Nagpur&specialty=oncology")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"National Cancer Institute", response.data)
        self.assertIn(b"Unverified", response.data)
        self.assertEqual(self.client.get("/doctors").status_code, 200)
        self.assertIn(b"No verified provider has published an appointment slot", self.client.get("/doctors").data)
        self.assertEqual(self.client.get("/cancer-care").status_code, 200)
        self.assertEqual(self.client.get("/dialysis-care").status_code, 200)
        self.assertEqual(self.client.get("/blood-banks").status_code, 200)
        blood_page = self.client.get("/blood-connect")
        self.assertEqual(blood_page.status_code, 200)
        self.assertIn(b"Example City Blood Centre (Fictional Demo)", blood_page.data)

    def test_app_shell_home_navigation_and_pwa_assets_render(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Care, connected.", home.data)
        self.assertIn(b"Discover", home.data)
        self.assertIn(b"Bookings", home.data)
        self.assertIn(b"Blood Connect", home.data)
        self.assertIn(b"Nearby care", home.data)
        self.assertIn(b"National Cancer Institute Nagpur", home.data)
        self.assertIn(b"manifest.webmanifest", home.data)
        self.assertIn(b"assistant-language", home.data)

        manifest = self.client.get("/static/manifest.webmanifest")
        self.assertEqual(manifest.status_code, 200)
        self.assertIn(b"standalone", manifest.data)
        self.assertIn(b"jeevansetu-192.png", manifest.data)
        self.assertIn(b"jeevansetu-512.png", manifest.data)
        self.assertEqual(self.client.get("/static/icons/jeevansetu.svg").status_code, 200)
        self.assertEqual(self.client.get("/static/icons/jeevansetu-192.png").status_code, 200)
        self.assertEqual(self.client.get("/static/icons/jeevansetu-512.png").status_code, 200)
        self.assertEqual(self.client.get("/static/icons/apple-touch-icon.png").status_code, 200)
        self.assertEqual(self.client.get("/static/offline.html").status_code, 200)

        service_worker = self.client.get("/service-worker.js")
        self.assertEqual(service_worker.status_code, 200)
        self.assertEqual(service_worker.headers["Service-Worker-Allowed"], "/")
        self.assertIn(b"request.mode === \"navigate\"", service_worker.data)

    def test_patient_home_uses_only_the_authenticated_patient_appointments(self):
        self.register()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome back, Test", response.data)
        self.assertIn(b"Registration details", response.data)
        self.assertIn(b"Medical reports", response.data)
        self.assertIn(b"No upcoming appointments", response.data)

    def test_patient_registration_creates_registration_number_and_mobile_access(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        with get_db(self.database_path) as db:
            user = db.execute("SELECT * FROM users WHERE email = ?", ("patient@example.test",)).fetchone()
            profile = db.execute(
                "SELECT * FROM patient_profiles WHERE user_id = ?", (user["id"],)
            ).fetchone()
        self.assertTrue(profile["registration_number"].startswith("JSN-"))
        self.assertEqual(profile["area_city"], "Nagpur")
        self.assertEqual(profile["care_category"], "cancer")
        self.assertTrue(user["password_hash"].startswith("scrypt:"))
        self.assertIn(profile["registration_number"].encode(), response.data)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/patient/dashboard").status_code, 200)

    def test_dashboard_shows_private_appointment_counts_history_and_editable_profile(self):
        self.assertEqual(self.client.get("/patient/dashboard").status_code, 302)
        self.register()
        doctor_id, slot_ids = self.verified_doctor_slots(count=4)
        with get_db(self.database_path) as db:
            own_id = db.execute(
                "SELECT id FROM users WHERE email = ?", ("patient@example.test",)
            ).fetchone()["id"]
            statuses = ("Pending", "Completed", "Cancelled")
            for slot_id, status in zip(slot_ids[:3], statuses, strict=True):
                db.execute(
                    """INSERT INTO appointments
                       (patient_id, doctor_id, slot_id, status) VALUES (?, ?, ?, ?)""",
                    (own_id, doctor_id, slot_id, status),
                )
            other_hospital = db.execute(
                """INSERT INTO hospitals
                   (name, address, city, verified, is_demo)
                   VALUES ('Other patient private facility', 'Secret address', 'Nagpur', 1, 0)"""
            ).lastrowid
            other_doctor = db.execute(
                """INSERT INTO doctors
                   (name, specialty, hospital_id, verified, is_demo)
                   VALUES ('Other patient private clinician', 'Sensitive specialty', ?, 1, 0)""",
                (other_hospital,),
            ).lastrowid
            other_patient = db.execute(
                """INSERT INTO users (name, email, password_hash, role)
                   VALUES ('Other Patient', 'other-patient@example.test', 'not-a-login-hash', 'patient')"""
            ).lastrowid
            db.execute(
                """INSERT INTO appointments (patient_id, doctor_id, slot_id, status)
                   VALUES (?, ?, ?, 'Pending')""",
                (other_patient, other_doctor, slot_ids[3]),
            )

        response = self.client.get("/patient/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Total appointments", response.data)
        self.assertIn(b"Completed appointments", response.data)
        self.assertIn(b"Cancelled appointments", response.data)
        self.assertIn(b"Verified Test Doctor", response.data)
        self.assertNotIn(b"Other patient private facility", response.data)
        self.assertNotIn(b"Other patient private clinician", response.data)

        saved = self.client.post("/patient/dashboard", data={
            "csrf_token": self.csrf(),
            "name": "Updated Patient Name",
            "area_city": "Dharampeth, Nagpur",
            "contact_email": "updated@example.test",
        }, follow_redirects=True)
        self.assertEqual(saved.status_code, 200)
        self.assertIn(b"Your profile details were updated", saved.data)
        with get_db(self.database_path) as db:
            user = db.execute("SELECT name FROM users WHERE id = ?", (own_id,)).fetchone()
            profile = db.execute(
                "SELECT area_city, contact_email, mobile FROM patient_profiles WHERE user_id = ?",
                (own_id,),
            ).fetchone()
        self.assertEqual(user["name"], "Updated Patient Name")
        self.assertEqual(profile["area_city"], "Dharampeth, Nagpur")
        self.assertEqual(profile["contact_email"], "updated@example.test")
        self.assertEqual(profile["mobile"], "+919876543201")

    def test_directory_search_filters_importable_ownership_and_handles_sql_like_input(self):
        with get_db(self.database_path) as db:
            for name, area, owner, phone in (
                ("Government Oncology Unit", "Sitabuldi", "government", "+91 7111 222333"),
                ("Private Kidney Centre", "Dharampeth", "private", "+91 7111 333444"),
            ):
                db.execute(
                    """INSERT INTO healthcare_directory
                       (name, category, address, city, area, phone, ownership_type,
                        specialty, services, source_url, verification_status)
                       VALUES (?, 'hospital', '1 Verified Road', 'Nagpur', ?, ?, ?,
                               'Oncology / nephrology', 'Cancer and dialysis',
                               'https://facility.example.test/', 'verified')""",
                    (name, area, phone, owner),
                )
        government = self.client.get("/directory?ownership=government&service=oncology")
        self.assertEqual(government.status_code, 200)
        self.assertIn(b"Government Oncology Unit", government.data)
        self.assertNotIn(b"Private Kidney Centre", government.data)

        private_by_area = self.client.get("/directory?area=Dharampeth&sort=area")
        self.assertIn(b"Private Kidney Centre", private_by_area.data)
        self.assertNotIn(b"Government Oncology Unit", private_by_area.data)

        phone_search = self.client.get("/directory?q=7111%20222333")
        self.assertIn(b"Government Oncology Unit", phone_search.data)
        injection_search = self.client.get("/directory?q=%25%27%20OR%201%3D1%20--")
        self.assertIn(b"No directory records match", injection_search.data)

    def test_provider_appointment_cancellation_is_scoped_to_patient_owner(self):
        self.register()
        with get_db(self.database_path) as db:
            owner_id = db.execute(
                "SELECT id FROM users WHERE email = ?", ("patient@example.test",)
            ).fetchone()["id"]
            other_id = db.execute(
                """INSERT INTO users (name, email, password_hash, role)
                   VALUES ('Another Patient', 'another@example.test', 'unused', 'patient')"""
            ).lastrowid
            listing_id = db.execute(
                """INSERT INTO healthcare_directory
                   (name, category, city, source_url, verification_status)
                   VALUES ('Verified Provider', 'hospital', 'Nagpur',
                           'https://provider.example.test/', 'verified')"""
            ).lastrowid
            slot_id = db.execute(
                """INSERT INTO provider_slots (listing_id, slot_at, published_by)
                   VALUES (?, ?, ?)""",
                (
                    listing_id,
                    (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT10:00"),
                    owner_id,
                ),
            ).lastrowid
            appointment_id = db.execute(
                """INSERT INTO provider_appointments (patient_id, listing_id, slot_id)
                   VALUES (?, ?, ?)""",
                (owner_id, listing_id, slot_id),
            ).lastrowid

        other_client = self.app.test_client()
        with other_client.session_transaction() as session:
            session["user_id"] = other_id
            session["csrf_token"] = "other-client-csrf"
        forbidden = other_client.post(
            f"/provider-appointments/{appointment_id}/cancel",
            data={"csrf_token": "other-client-csrf"},
        )
        self.assertEqual(forbidden.status_code, 404)

        cancelled = self.client.post(
            f"/provider-appointments/{appointment_id}/cancel",
            data={"csrf_token": self.csrf()},
        )
        self.assertEqual(cancelled.status_code, 302)
        with get_db(self.database_path) as db:
            status = db.execute(
                "SELECT status FROM provider_appointments WHERE id = ?",
                (appointment_id,),
            ).fetchone()["status"]
        self.assertEqual(status, "Cancelled")

    def test_returning_patient_demo_code_opens_only_matching_patient_dashboard(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.client.get("/patient/access")
        response = self.client.post("/patient/access", data={
            "csrf_token": self.csrf(),
            "phase": "request",
            "mobile": "+91 98765 43201",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Local demo verification", response.data)
        match = re.search(rb"Local demo code:</strong> <code>(\d{6})", response.data)
        self.assertIsNotNone(match)
        code = match.group(1).decode()
        verified = self.client.post("/patient/access", data={
            "csrf_token": self.csrf(),
            "phase": "verify",
            "mobile": "+91 98765 43201",
            "code": code,
        })
        self.assertEqual(verified.status_code, 302)
        self.assertEqual(verified.headers["Location"], "/patient/dashboard")
        self.assertEqual(self.client.get("/patient/dashboard").status_code, 200)

        other_client = self.app.test_client()
        other_client.get("/patient/access")
        unknown = other_client.post("/patient/access", data={
            "csrf_token": self.csrf(other_client),
            "phase": "request",
            "mobile": "+91 98765 43999",
        })
        self.assertIn(b"Local demo code:", unknown.data)
        self.assertIn(b"does not confirm whether a registration matches", unknown.data)
        self.assertIn(b"does not confirm whether a registration matches", response.data)
        self.assertIn(b"Local demo request processed. No SMS was sent.", response.data)
        self.assertIn(b"Local demo request processed. No SMS was sent.", unknown.data)
        unknown_code = re.search(rb"Local demo code:</strong> <code>(\d{6})", unknown.data)
        self.assertIsNotNone(unknown_code)
        denied = other_client.post("/patient/access", data={
            "csrf_token": self.csrf(other_client),
            "phase": "verify",
            "mobile": "+91 98765 43999",
            "code": unknown_code.group(1).decode(),
        })
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(other_client.get("/patient/dashboard").status_code, 302)

    def enable_twilio(self):
        self.app.config.update(
            SMS_OTP_MODE="twilio",
            TWILIO_ACCOUNT_SID="AC" + "1" * 32,
            TWILIO_AUTH_TOKEN="test-token-not-a-real-credential",
            TWILIO_VERIFY_SERVICE_SID="VA" + "2" * 32,
        )

    def post_otp_request(self, mobile, client=None):
        client = client or self.client
        return client.post("/patient/access", data={
            "csrf_token": self.csrf(client),
            "phase": "request",
            "mobile": mobile,
        })

    def post_otp_verification(self, mobile, code, client=None):
        client = client or self.client
        return client.post("/patient/access", data={
            "csrf_token": self.csrf(client),
            "phase": "verify",
            "mobile": mobile,
            "code": code,
        })

    def test_twilio_otp_normalizes_phone_and_only_approved_code_authenticates(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.enable_twilio()
        with patch("app.TwilioClient") as client_factory:
            response = self.post_otp_request("(98765) 43201")
            self.assertEqual(response.status_code, 200)
            client_factory.return_value.verify.v2.services.return_value.verifications.create.assert_called_once_with(
                to="+919876543201", channel="sms"
            )
            self.assertIn(b"Delivery is not confirmed", response.data)
            self.assertNotIn(b"Local demo code:", response.data)

            check = client_factory.return_value.verify.v2.services.return_value
            check.verification_checks.create.return_value.status = "pending"
            wrong_code = self.post_otp_verification("+919876543201", "123456")
            self.assertEqual(wrong_code.status_code, 200)
            self.assertIn(b"The code is invalid, expired, or could not be confirmed", wrong_code.data)
            self.assertEqual(self.client.get("/patient/dashboard").status_code, 302)

            check.verification_checks.create.return_value.status = "approved"
            accepted = self.post_otp_verification("+919876543201", "654321")
            self.assertEqual(accepted.status_code, 302)
            self.assertEqual(accepted.headers["Location"], "/patient/dashboard")
            self.assertEqual(self.client.get("/patient/dashboard").status_code, 200)

    def test_twilio_missing_configuration_and_invalid_phone_fail_closed(self):
        self.enable_twilio()
        self.app.config["TWILIO_AUTH_TOKEN"] = ""
        missing = self.post_otp_request("+919876543201")
        self.assertIn(b"no SMS was sent", missing.data)
        with get_db(self.database_path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM patient_otp_challenges").fetchone()[0],
                0,
            )

        self.app.config["TWILIO_AUTH_TOKEN"] = "configured-test-token"
        invalid = self.post_otp_request("+911234567890")
        self.assertIn(b"Enter a valid Indian mobile number", invalid.data)
        with get_db(self.database_path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM patient_otp_challenges").fetchone()[0],
                0,
            )

    def test_twilio_provider_failure_is_not_reported_as_sms_delivery(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.enable_twilio()
        with patch("app.TwilioClient") as client_factory:
            client_factory.return_value.verify.v2.services.return_value.verifications.create.side_effect = (
                RequestsConnectionError("private provider detail")
            )
            response = self.post_otp_request("+919876543201")
        self.assertIn(b"Delivery is not confirmed", response.data)
        self.assertNotIn(b"private provider detail", response.data)
        with get_db(self.database_path) as db:
            challenge = db.execute(
                "SELECT status FROM patient_otp_challenges WHERE mobile = ?",
                ("+919876543201",),
            ).fetchone()
        self.assertEqual(challenge["status"], "failed")

    def test_twilio_verification_provider_error_does_not_authenticate(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.enable_twilio()
        with patch("app.TwilioClient") as client_factory:
            service = client_factory.return_value.verify.v2.services.return_value
            self.post_otp_request("+919876543201")
            service.verification_checks.create.side_effect = RequestsConnectionError(
                "private verification detail"
            )
            response = self.post_otp_verification("+919876543201", "123456")
        self.assertIn(b"The code is invalid, expired, or could not be confirmed", response.data)
        self.assertNotIn(b"private verification detail", response.data)
        self.assertEqual(self.client.get("/patient/dashboard").status_code, 302)

    def test_expired_twilio_challenge_is_not_sent_to_provider_for_check(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.enable_twilio()
        with patch("app.TwilioClient") as client_factory:
            self.post_otp_request("+919876543201")
            with get_db(self.database_path) as db:
                db.execute(
                    "UPDATE patient_otp_challenges SET expires_at = ? WHERE mobile = ?",
                    ("2000-01-01T00:00:00", "+919876543201"),
                )
            response = self.post_otp_verification("+919876543201", "123456")
        self.assertIn(b"invalid, expired, or could not be confirmed", response.data)
        client_factory.return_value.verify.v2.services.return_value.verification_checks.create.assert_not_called()
        self.assertEqual(self.client.get("/patient/dashboard").status_code, 302)

    def test_twilio_resend_cooldown_and_request_limit(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.enable_twilio()
        with patch("app.TwilioClient") as client_factory:
            self.post_otp_request("+919876543201")
            cooldown = self.post_otp_request("+919876543201")
            self.assertIn(b"wait", cooldown.data)
            create = client_factory.return_value.verify.v2.services.return_value.verifications.create
            self.assertEqual(create.call_count, 1)

            for _ in range(4):
                with get_db(self.database_path) as db:
                    db.execute(
                        "UPDATE patient_otp_challenges SET created_at = datetime('now', '-61 seconds') "
                        "WHERE mobile = ?",
                        ("+919876543201",),
                    )
                self.post_otp_request("+919876543201")
            with get_db(self.database_path) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM patient_otp_challenges WHERE mobile = ?",
                        ("+919876543201",),
                    ).fetchone()[0],
                    5,
                )
                db.execute(
                    "UPDATE patient_otp_challenges SET created_at = datetime('now', '-61 seconds') "
                    "WHERE mobile = ?",
                    ("+919876543201",),
                )
            limited = self.post_otp_request("+919876543201")
            self.assertIn(b"Too many verification requests", limited.data)
            self.assertEqual(create.call_count, 5)

    def test_twilio_wrong_code_attempts_expire_challenge(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.enable_twilio()
        with patch("app.TwilioClient") as client_factory:
            self.post_otp_request("+919876543201")
            check = client_factory.return_value.verify.v2.services.return_value
            check.verification_checks.create.return_value.status = "pending"
            for _ in range(5):
                response = self.post_otp_verification("+919876543201", "123456")
                self.assertIn(b"The code is invalid, expired, or could not be confirmed", response.data)
            locked = self.post_otp_verification("+919876543201", "123456")
            self.assertIn(b"invalid, expired, or could not be confirmed", locked.data)
            self.assertEqual(check.verification_checks.create.call_count, 5)
        with get_db(self.database_path) as db:
            challenge = db.execute(
                "SELECT attempts FROM patient_otp_challenges WHERE mobile = ?",
                ("+919876543201",),
            ).fetchone()
        self.assertEqual(challenge["attempts"], 5)

    def test_twilio_approved_code_cannot_open_another_patient_account(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.enable_twilio()
        with get_db(self.database_path) as db:
            db.execute(
                """INSERT INTO patient_otp_challenges
                   (mobile, code_hash, expires_at, provider, status)
                   VALUES (?, ?, ?, 'twilio', 'pending')""",
                (
                    "+919876543299",
                    generate_password_hash("not-a-real-code"),
                    (datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds"),
                ),
            )
        with patch("app.TwilioClient") as client_factory:
            client_factory.return_value.verify.v2.services.return_value.verification_checks.create.return_value.status = (
                "approved"
            )
            response = self.post_otp_verification("+919876543299", "123456")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/patient/dashboard").status_code, 302)

    def test_login_rejects_external_and_malformed_next_urls(self):
        with get_db(self.database_path) as db:
            db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                ("Admin", "admin@example.test", generate_password_hash("staff password")),
            )
        for next_url in ("https://example.invalid/", "//example.invalid/", "http://["):
            with self.subTest(next_url=next_url):
                client = self.app.test_client()
                client.get("/login")
                response = client.post("/login", query_string={"next": next_url}, data={
                    "csrf_token": self.csrf(client),
                    "email": "admin@example.test",
                    "password": "staff password",
                })
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/")

    def test_hospital_submission_stays_hidden_until_admin_verifies(self):
        self.register()
        response = self.client.post("/provider/register", data={
            "csrf_token": self.csrf(),
            "name": "Community Clinic",
            "category": "hospital",
            "address": "99 Sample Street",
            "city": "Nagpur",
            "area": "Camp",
            "specialty": "Oncology",
            "source_url": "https://clinic.example.test/",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Community Clinic", response.data)
        with get_db(self.database_path) as db:
            listing_id = db.execute(
                "SELECT id FROM healthcare_directory WHERE name = ?", ("Community Clinic",)
            ).fetchone()["id"]
            db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                ("Admin", "admin@example.test", generate_password_hash("admin-password")),
            )
        admin_client = self.app.test_client()
        admin_client.get("/login")
        admin_client.post("/login", data={
            "csrf_token": self.csrf(admin_client),
            "email": "admin@example.test",
            "password": "admin-password",
        }, follow_redirects=True)
        response = admin_client.post(
            f"/admin/directory/{listing_id}/verify",
            data={"csrf_token": self.csrf(admin_client)},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Community Clinic", self.client.get("/hospitals").data)

    def test_verified_provider_publishes_slot_and_handles_only_own_requests(self):
        self.register()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.client.get("/provider/register")
        submission = self.client.post("/provider/register", data={
            "csrf_token": self.csrf(),
            "name": "Verified Test Clinic",
            "category": "hospital",
            "address": "1 Test Road",
            "city": "Nagpur",
            "area": "Dharampeth",
            "phone": "+91 712 555 0100",
            "website": "https://clinic.example.test/",
            "specialty": "Nephrology and dialysis",
            "source_url": "https://clinic.example.test/services",
        })
        self.assertEqual(submission.status_code, 302)
        with get_db(self.database_path) as db:
            listing_id = db.execute(
                "SELECT id FROM healthcare_directory WHERE name = ?",
                ("Verified Test Clinic",),
            ).fetchone()["id"]
            db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                ("Test Admin", "admin@example.test", generate_password_hash("admin password")),
            )
        admin_client = self.app.test_client()
        admin_client.get("/login")
        admin_client.post("/login", data={
            "csrf_token": self.csrf(admin_client),
            "email": "admin@example.test",
            "password": "admin password",
        })
        admin_client.get("/admin")
        verified = admin_client.post(
            f"/admin/directory/{listing_id}/verify",
            data={"csrf_token": self.csrf(admin_client)},
        )
        self.assertEqual(verified.status_code, 302)
        runner = self.app.test_cli_runner()
        staff_result = runner.invoke(
            args=["create-staff"],
            input=(
                "Clinic Staff\nclinic@example.test\nhospital\n"
                f"{listing_id}\nclinic password\nclinic password\n"
            ),
        )
        self.assertEqual(staff_result.exit_code, 0, staff_result.output)
        with get_db(self.database_path) as db:
            provider_user_id = db.execute(
                "SELECT id FROM users WHERE email = ?", ("clinic@example.test",)
            ).fetchone()["id"]
            self.assertEqual(
                db.execute(
                    "SELECT listing_id FROM provider_accounts WHERE user_id = ?",
                    (provider_user_id,),
                ).fetchone()["listing_id"],
                listing_id,
            )

        provider_client = self.app.test_client()
        provider_client.get("/login")
        provider_client.post("/login", data={
            "csrf_token": self.csrf(provider_client),
            "email": "clinic@example.test",
            "password": "clinic password",
        })
        provider_client.get("/provider/listing")
        slot_time = (datetime.now() + timedelta(days=3)).replace(
            second=0, microsecond=0
        ).strftime("%Y-%m-%dT%H:%M")
        published = provider_client.post("/provider/listing", data={
            "csrf_token": self.csrf(provider_client),
            "form_type": "slot",
            "slot_at": slot_time,
        })
        self.assertEqual(published.status_code, 302)
        with get_db(self.database_path) as db:
            slot_id = db.execute(
                "SELECT id FROM provider_slots WHERE listing_id = ?", (listing_id,)
            ).fetchone()["id"]

        access_request = self.client.post("/patient/access", data={
            "csrf_token": self.csrf(),
            "phase": "request",
            "mobile": "+91 98765 43201",
        })
        code_match = re.search(
            rb"Local demo code:</strong> <code>(\d{6})", access_request.data
        )
        self.assertIsNotNone(code_match)
        verified_patient = self.client.post("/patient/access", data={
            "csrf_token": self.csrf(),
            "phase": "verify",
            "mobile": "+91 98765 43201",
            "code": code_match.group(1).decode(),
        })
        self.assertEqual(verified_patient.status_code, 302)
        self.client.get("/patient/dashboard")
        requested = self.client.post("/appointments", data={
            "csrf_token": self.csrf(),
            "booking_type": "provider",
            "slot_id": str(slot_id),
            "visit_reason": "Appointment request",
        })
        self.assertEqual(requested.status_code, 302)
        with get_db(self.database_path) as db:
            appointment = db.execute(
                "SELECT id, status FROM provider_appointments WHERE slot_id = ?",
                (slot_id,),
            ).fetchone()
        self.assertEqual(appointment["status"], "Requested")
        self.assertIn(b"awaiting hospital confirmation", self.client.get("/appointments").data)

        provider_client.get("/provider/listing")
        confirmed = provider_client.post(
            f"/provider/appointments/{appointment['id']}/status",
            data={"csrf_token": self.csrf(provider_client), "status": "Confirmed"},
        )
        self.assertEqual(confirmed.status_code, 302)
        with get_db(self.database_path) as db:
            status = db.execute(
                "SELECT status FROM provider_appointments WHERE id = ?", (appointment["id"],)
            ).fetchone()["status"]
        self.assertEqual(status, "Confirmed")
        with get_db(self.database_path) as db:
            other_listing_id = db.execute(
                """INSERT INTO healthcare_directory
                   (name, category, city, source_url, verification_status)
                   VALUES (?, 'hospital', 'Nagpur', ?, 'verified')""",
                ("Another Verified Clinic", "https://other-clinic.example.test/"),
            ).lastrowid
            patient_id = db.execute(
                "SELECT user_id FROM patient_profiles WHERE mobile = ?",
                ("+919876543201",),
            ).fetchone()["user_id"]
            other_slot_id = db.execute(
                """INSERT INTO provider_slots (listing_id, slot_at, published_by)
                   VALUES (?, ?, ?)""",
                (other_listing_id, slot_time, provider_user_id),
            ).lastrowid
            other_appointment_id = db.execute(
                """INSERT INTO provider_appointments (patient_id, listing_id, slot_id)
                   VALUES (?, ?, ?)""",
                (patient_id, other_listing_id, other_slot_id),
            ).lastrowid
        unauthorized = provider_client.post(
            f"/provider/appointments/{other_appointment_id}/status",
            data={"csrf_token": self.csrf(provider_client), "status": "Confirmed"},
        )
        self.assertEqual(unauthorized.status_code, 404)
        with get_db(self.database_path) as db:
            other_status = db.execute(
                "SELECT status FROM provider_appointments WHERE id = ?",
                (other_appointment_id,),
            ).fetchone()["status"]
        self.assertEqual(other_status, "Requested")

    def test_active_slot_cannot_be_double_booked_and_cancel_releases_it(self):
        self.register()
        _, slot_ids = self.verified_doctor_slots()
        slot_id = slot_ids[0]
        first = self.client.post("/appointments", data={
            "csrf_token": self.csrf(), "slot_id": str(slot_id), "visit_reason": "Routine visit",
        }, follow_redirects=True)
        self.assertIn(b"Appointment requested", first.data)
        with get_db(self.database_path) as db:
            appointment_id = db.execute("SELECT id FROM appointments").fetchone()["id"]
        consultation = self.client.get(f"/appointments/{appointment_id}/consultation")
        self.assertEqual(consultation.status_code, 200)
        self.assertIn(b"No video service is integrated", consultation.data)
        second = self.client.post("/appointments", data={
            "csrf_token": self.csrf(), "slot_id": str(slot_id), "visit_reason": "",
        }, follow_redirects=True)
        self.assertIn(b"just been booked", second.data)
        with get_db(self.database_path) as db:
            appointment = db.execute("SELECT id FROM appointments").fetchone()
        response = self.client.post(
            f"/appointments/{appointment['id']}/cancel",
            data={"csrf_token": self.csrf()},
        )
        self.assertEqual(response.status_code, 302)
        self.client.post("/appointments", data={
            "csrf_token": self.csrf(), "slot_id": str(slot_id), "visit_reason": "",
        })
        with get_db(self.database_path) as db:
            active_appointment = db.execute(
                "SELECT id FROM appointments WHERE status = 'Pending'"
            ).fetchone()
        self.client.post(
            f"/appointments/{active_appointment['id']}/cancel",
            data={"csrf_token": self.csrf()},
        )
        other_client = self.app.test_client()
        other_client.get("/patient/register")
        other_client.post("/patient/register", data={
            "csrf_token": self.csrf(other_client),
            "name": "Second Patient",
            "mobile": "+919876543299",
            "age": "40",
            "area_city": "Nagpur",
            "privacy_consent": "yes",
        }, follow_redirects=True)
        response = other_client.post("/appointments", data={
            "csrf_token": self.csrf(other_client), "slot_id": str(slot_id), "visit_reason": "",
        })
        self.assertEqual(response.status_code, 302)

    def test_reschedule_moves_to_an_available_slot_for_same_doctor(self):
        self.register()
        _, slot_ids = self.verified_doctor_slots()
        self.client.post("/appointments", data={
            "csrf_token": self.csrf(), "slot_id": str(slot_ids[0]), "visit_reason": "",
        })
        with get_db(self.database_path) as db:
            appointment_id = db.execute("SELECT id FROM appointments").fetchone()["id"]
        response = self.client.post(
            f"/appointments/{appointment_id}/reschedule",
            data={"csrf_token": self.csrf(), "slot_id": str(slot_ids[1])},
            follow_redirects=True,
        )
        self.assertIn(b"Appointment rescheduled", response.data)
        with get_db(self.database_path) as db:
            current_slot_id = db.execute(
                "SELECT slot_id FROM appointments WHERE id = ?", (appointment_id,)
            ).fetchone()["slot_id"]
        self.assertEqual(current_slot_id, slot_ids[1])

    def test_expired_slots_are_not_offered_or_booked(self):
        self.register()
        _, slot_ids = self.verified_doctor_slots(count=1)
        with get_db(self.database_path) as db:
            db.execute(
                "UPDATE doctor_slots SET slot_at = ? WHERE id = ?",
                ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"), slot_ids[0]),
            )
        response = self.client.post("/appointments", data={
            "csrf_token": self.csrf(), "slot_id": str(slot_ids[0]), "visit_reason": "",
        }, follow_redirects=True)
        self.assertIn(b"slot is no longer available", response.data)
        with get_db(self.database_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM appointments").fetchone()[0], 0)

    def test_reports_are_private_and_upload_validates_consent_and_extension(self):
        self.register()
        denied = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "report": (io.BytesIO(b"image bytes"), "report.png"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"Consent is required", denied.data)
        invalid_file = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "consent": "yes",
            "report": (io.BytesIO(b"not a png"), "report.png"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"do not match the selected report type", invalid_file.data)
        uploaded = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "consent": "yes",
            "language": "hi",
            "report": (io.BytesIO(b"\x89PNG\r\n\x1a\nimage bytes"), "report.png"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(uploaded.status_code, 200)
        self.assertIn("रिपोर्ट से पढ़ने योग्य पाठ".encode("utf-8"), uploaded.data)
        self.assertIn(b"informational and must be reviewed", uploaded.data)

        with get_db(self.database_path) as db:
            other_user_id = db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Other Patient", "other@example.test", generate_password_hash("other password")),
            ).lastrowid
            db.execute(
                """INSERT INTO patient_profiles
                   (user_id, registration_number, mobile, age, area_city, privacy_consent)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (other_user_id, "JSN-2026-OTHER", "+919876543299", 35, "Nagpur"),
            )
        other_client = self.app.test_client()
        other_client.get("/patient/access")
        code_response = other_client.post("/patient/access", data={
            "csrf_token": self.csrf(other_client),
            "phase": "request",
            "mobile": "+919876543299",
        }, follow_redirects=True)
        code_match = re.search(rb"Local demo code:</strong>\s*<code>(\d{6})", code_response.data)
        self.assertIsNotNone(code_match)
        other_client.post("/patient/access", data={
            "csrf_token": self.csrf(other_client),
            "phase": "verify",
            "mobile": "+919876543299",
            "code": code_match.group(1).decode(),
        })
        with get_db(self.database_path) as db:
            report_id = db.execute("SELECT id FROM medical_reports").fetchone()["id"]
        self.assertEqual(other_client.get(f"/reports/{report_id}/download").status_code, 404)

    def test_unreadable_report_is_never_sent_to_external_ai(self):
        self.register()
        self.app.config.update({
            "AI_API_URL": "https://127.0.0.1:1/v1/chat/completions",
            "AI_API_KEY": "test-key",
            "AI_MODEL": "test-model",
        })
        response = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "consent": "yes",
            "external_ai_consent": "yes",
            "report": (io.BytesIO(b"\x89PNG\r\n\x1a\nimage bytes"), "scan.png"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"no external AI service was contacted", response.data)
        with get_db(self.database_path) as db:
            consent_purposes = [
                row["purpose"] for row in db.execute("SELECT purpose FROM consents")
            ]
            self.assertFalse(any("external AI" in purpose for purpose in consent_purposes))

    def test_readable_pdf_extracts_values_and_compares_only_printed_range(self):
        self.register()
        response = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "consent": "yes",
            "report": (
                io.BytesIO(self.text_pdf("Glucose 105 mg/dL Reference range: 70-99 mg/dL")),
                "lab-report.pdf",
            ),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Glucose", response.data)
        self.assertIn(b"105", response.data)
        self.assertIn(b"70-99 mg/dL", response.data)
        self.assertIn(b"Outside provided range", response.data)
        self.assertIn(b"not a diagnosis", response.data)

    def test_malformed_pdf_is_reported_as_unreadable(self):
        self.register()
        response = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "consent": "yes",
            "report": (io.BytesIO(b"%PDF-1.4\nmalformed"), "malformed.pdf"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Unreadable report", response.data)
        self.assertIn(b"No readable text was found", response.data)

    def test_upload_size_limit_returns_413(self):
        self.register()
        self.app.config["MAX_CONTENT_LENGTH"] = 1024
        response = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "consent": "yes",
            "report": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 2048), "large.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 413)
        self.app.config.update({"MAX_UPLOAD_SIZE": 32, "MAX_CONTENT_LENGTH": 1024 * 1024})
        response = self.client.post("/reports", data={
            "csrf_token": self.csrf(),
            "consent": "yes",
            "report": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 80), "large.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 413)

    def test_patient_pages_render_and_invalid_dates_are_rejected(self):
        self.register()
        for page in (
            "/", "/hospitals", "/doctors", "/appointments", "/cancer-care",
            "/dialysis-care", "/blood-connect", "/reports",
        ):
            with self.subTest(page=page):
                self.assertEqual(self.client.get(page).status_code, 200)
        response = self.client.post("/cancer-care", data={
            "csrf_token": self.csrf(),
            "care_consent": "yes",
            "clinician_confirmed_info": "Clinician-confirmed",
            "treatment_date": "2026-10-12",
            "follow_up_date": "2026-10-11",
        }, follow_redirects=True)
        self.assertIn(b"follow-up date cannot be earlier", response.data)

    def test_ai_assistant_page_and_floating_chat_are_available_with_clear_missing_key_error(self):
        self.app.config["OPENAI_API_KEY"] = ""
        page = self.client.get("/ai-assistant")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"AI Health Assistant", page.data)
        self.assertIn(b"JeevanSetu AI", page.data)
        self.assertIn(b"/api/ai-chat", page.data)
        self.assertIn(b"ai-chat-launcher", self.client.get("/").data)
        response = self.client.post(
            "/api/ai-chat", json={"message": "Hello"}, headers=self.csrf_headers()
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.get_json()["error"])

    def test_ai_chat_uses_openai_sdk_and_only_verified_directory_database_context(self):
        self.app.config.update({
            "OPENAI_API_KEY": "test-only-key",
            "OPENAI_MODEL": "test-model",
        })
        with get_db(self.database_path) as db:
            db.execute(
                """INSERT INTO healthcare_directory
                   (name, category, address, city, area, specialty, source_url,
                    verification_status)
                   VALUES (?, 'cancer', ?, 'Nagpur', 'Test Area', ?, ?, 'verified')""",
                (
                    "Assistant Test Oncology Centre",
                    "10 Test Street",
                    "Medical oncology",
                    "https://clinic.example.test/",
                ),
            )
            db.execute(
                """INSERT INTO healthcare_directory
                   (name, category, city, source_url, verification_status, potentially_duplicate)
                   VALUES (?, 'cancer', 'Nagpur', ?, 'verified', 1)""",
                ("Duplicate Hidden Hospital", "https://duplicate.example.test/"),
            )
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Verified directory data found."))]
        )
        with patch("app.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = completion
            response = self.client.post("/api/ai-chat", json={
                "message": "Find oncology hospitals near me",
                "language": "hi",
                "topic": "hospital",
                "facility_category": "cancer",
                "facility_location": "Nagpur",
            }, headers=self.csrf_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["response"], "Verified directory data found.")
        self.assertGreaterEqual(response.get_json()["directory_results"], 1)
        openai_client.assert_called_once_with(
            api_key="test-only-key", timeout=30, max_retries=1
        )
        call = openai_client.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(call["model"], "test-model")
        self.assertIn("Hindi", call["messages"][1]["content"])
        self.assertIn("Assistant Test Oncology Centre", call["messages"][1]["content"])
        self.assertNotIn("Duplicate Hidden Hospital", call["messages"][1]["content"])

    def test_ai_report_upload_requires_consent_and_processes_pdf_without_persisting_it(self):
        self.app.config.update({"OPENAI_API_KEY": "test-only-key"})
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="The report lists a glucose value."))]
        )
        with patch("app.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = completion
            denied = self.client.post("/api/ai-chat", data={
                "csrf_token": self.csrf(),
                "topic": "report",
                "report": (io.BytesIO(self.text_pdf("Glucose 90 mg/dL Reference range: 70-99 mg/dL")), "report.pdf"),
            }, content_type="multipart/form-data")
            self.assertEqual(denied.status_code, 400)
            openai_client.assert_not_called()

            uploaded = self.client.post("/api/ai-chat", data={
                "csrf_token": self.csrf(),
                "topic": "report",
                "language": "en",
                "report_consent": "yes",
                "report": (io.BytesIO(self.text_pdf("Glucose 90 mg/dL Reference range: 70-99 mg/dL")), "report.pdf"),
            }, content_type="multipart/form-data")
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.get_json()["response"], "The report lists a glucose value.")
        call = openai_client.return_value.chat.completions.create.call_args.kwargs
        self.assertIn("Glucose 90 mg/dL", call["messages"][1]["content"])
        with get_db(self.database_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM medical_reports").fetchone()[0], 0)

    def test_ai_chat_rejects_invalid_inputs_and_sends_consented_validated_images(self):
        self.app.config["OPENAI_API_KEY"] = "test-only-key"
        empty = self.client.post(
            "/api/ai-chat", json={"message": ""}, headers=self.csrf_headers()
        )
        self.assertEqual(empty.status_code, 400)
        invalid = self.client.post(
            "/api/ai-chat",
            json={"message": "hi", "language": "xx"},
            headers=self.csrf_headers(),
        )
        self.assertEqual(invalid.status_code, 400)

        with patch("app.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.side_effect = OpenAIError(
                "simulated provider failure"
            )
            provider_error = self.client.post(
                "/api/ai-chat",
                json={"message": "Hello"},
                headers=self.csrf_headers(),
            )
        self.assertEqual(provider_error.status_code, 502)
        self.assertIn("provider could not complete", provider_error.get_json()["error"])

        invalid_image = self.client.post("/api/ai-chat", data={
            "csrf_token": self.csrf(),
            "topic": "report",
            "report_consent": "yes",
            "report": (io.BytesIO(b"\x89PNG\r\n\x1a\ninvalid"), "scan.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(invalid_image.status_code, 400)

        image_bytes = io.BytesIO()
        Image.new("RGB", (1, 1), color=(30, 120, 180)).save(image_bytes, format="PNG")
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="The image shows report text to discuss with a clinician."))]
        )
        with patch("app.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = completion
            denied = self.client.post("/api/ai-chat", data={
                "csrf_token": self.csrf(),
                "topic": "report",
                "report": (io.BytesIO(image_bytes.getvalue()), "scan.png"),
            }, content_type="multipart/form-data")
            self.assertEqual(denied.status_code, 400)
            openai_client.assert_not_called()

            image = self.client.post("/api/ai-chat", data={
                "csrf_token": self.csrf(),
                "topic": "report",
                "report_consent": "yes",
                "report": (io.BytesIO(image_bytes.getvalue()), "scan.png"),
            }, content_type="multipart/form-data")
        self.assertEqual(image.status_code, 200)
        self.assertIn("clinician", image.get_json()["response"])
        content = openai_client.return_value.chat.completions.create.call_args.kwargs[
            "messages"
        ][1]["content"]
        self.assertIsInstance(content, list)
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_doctor_can_only_view_and_update_appointments_for_linked_profile(self):
        self.register()
        doctor_id, slot_ids = self.verified_doctor_slots(count=1)
        with get_db(self.database_path) as db:
            db.execute(
                "UPDATE doctors SET consultation_mode = 'In-person' WHERE id = ?",
                (doctor_id,),
            )
        self.client.post("/appointments", data={
            "csrf_token": self.csrf(), "slot_id": str(slot_ids[0]), "visit_reason": "Routine",
        })
        with get_db(self.database_path) as db:
            doctor_user = db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'doctor')",
                ("Demo Doctor", "doctor@example.test", generate_password_hash("doctor password")),
            )
            db.execute("UPDATE doctors SET user_id = ? WHERE id = ?", (doctor_user.lastrowid, doctor_id))
            appointment_id = db.execute("SELECT id FROM appointments").fetchone()["id"]
        doctor_client = self.app.test_client()
        doctor_client.get("/login")
        doctor_client.post("/login", data={
            "csrf_token": self.csrf(doctor_client),
            "email": "doctor@example.test",
            "password": "doctor password",
        }, follow_redirects=True)
        self.assertIn(b"Test Patient", doctor_client.get("/doctor/appointments").data)
        response = doctor_client.post(
            f"/appointments/{appointment_id}/status",
            data={"csrf_token": self.csrf(doctor_client), "status": "Confirmed"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/doctor/appointments")
        self.assertEqual(self.client.get("/doctor/appointments").status_code, 403)
        self.assertEqual(doctor_client.get("/reports").status_code, 403)

    def test_admin_can_update_appointment_status_and_return_to_admin_dashboard(self):
        self.register()
        _, slot_ids = self.verified_doctor_slots(count=1)
        self.client.post("/appointments", data={
            "csrf_token": self.csrf(),
            "slot_id": str(slot_ids[0]),
            "visit_reason": "Routine",
        })
        with get_db(self.database_path) as db:
            appointment_id = db.execute("SELECT id FROM appointments").fetchone()["id"]
            db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                ("Demo Admin", "admin@example.test", generate_password_hash("admin password")),
            )
        admin_client = self.app.test_client()
        admin_client.get("/login")
        admin_client.post("/login", data={
            "csrf_token": self.csrf(admin_client),
            "email": "admin@example.test",
            "password": "admin password",
        })
        self.assertEqual(admin_client.get("/admin").status_code, 200)
        response = admin_client.post(
            f"/appointments/{appointment_id}/status",
            data={"csrf_token": self.csrf(admin_client), "status": "Confirmed"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin")
        with get_db(self.database_path) as db:
            status = db.execute(
                "SELECT status FROM appointments WHERE id = ?", (appointment_id,)
            ).fetchone()["status"]
        self.assertEqual(status, "Confirmed")

    def test_cancer_dialysis_and_blood_entries_persist(self):
        self.register()
        care = self.client.post("/cancer-care", data={
            "csrf_token": self.csrf(),
            "clinician_confirmed_info": "Information confirmed by my clinician",
            "treatment_name": "Follow-up visit",
            "treatment_date": "2026-10-12",
            "follow_up_date": "2026-11-12",
            "clinician_name": "Dr. Example",
            "care_consent": "yes",
        }, follow_redirects=True)
        self.assertIn(b"Cancer-care entry saved", care.data)
        dialysis = self.client.post("/dialysis-care", data={
            "csrf_token": self.csrf(),
            "session_at": "2026-10-13",
            "status": "Upcoming",
            "clinician_name": "Care team",
            "care_consent": "yes",
        }, follow_redirects=True)
        self.assertIn(b"Dialysis schedule entry saved", dialysis.data)
        blood = self.client.post("/blood-connect", data={
            "csrf_token": self.csrf(),
            "form_type": "request",
            "blood_group": "B+",
            "hospital_location": "Example Hospital",
            "city": "Pune",
            "urgency": "Urgent",
            "contact_name": "Private Contact",
            "contact_phone": "+91 98765 43210",
            "request_consent": "yes",
        }, follow_redirects=True)
        self.assertIn(b"Request saved.", blood.data)
        self.assertNotIn(b"Private Contact", blood.data)
        with get_db(self.database_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM cancer_records").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM dialysis_schedules").fetchone()[0], 1)
            request_id = db.execute(
                "SELECT id FROM blood_requests WHERE contact_name = ?", ("Private Contact",)
            ).fetchone()["id"]
        updated = self.client.post(
            f"/blood-connect/{request_id}/status",
            data={"csrf_token": self.csrf(), "status": "Resolved"},
            follow_redirects=True,
        )
        self.assertIn(b"does not confirm that blood is available", updated.data)
        with get_db(self.database_path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT status FROM blood_requests WHERE id = ?", (request_id,)
                ).fetchone()["status"],
                "Resolved",
            )
            request_row = db.execute("SELECT user_id, contact_phone FROM blood_requests WHERE is_demo = 0").fetchone()
            self.assertEqual(request_row["user_id"], db.execute("SELECT id FROM users WHERE email = ?", (
                "patient@example.test",
            )).fetchone()["id"])
            self.assertEqual(request_row["contact_phone"], "+91 98765 43210")
            blood_request_id = db.execute(
                "SELECT id FROM blood_requests WHERE is_demo = 0"
            ).fetchone()["id"]
        public_page = self.client.get("/blood-connect")
        self.assertNotIn(b"+91 98765 43210", public_page.data)
        resolved = self.client.post(
            f"/blood-connect/{blood_request_id}/status",
            data={"csrf_token": self.csrf(), "status": "Resolved"},
            follow_redirects=True,
        )
        self.assertIn(b"does not confirm that blood is available", resolved.data)
        self.assertIn(b"Resolved", resolved.data)
        anonymous_page = self.app.test_client().get("/blood-connect")
        self.assertNotIn(b"Example Hospital", anonymous_page.data)

    def test_donor_interest_requires_consent_and_is_saved_privately(self):
        self.register()
        response = self.client.post("/blood-connect", data={
            "csrf_token": self.csrf(),
            "form_type": "donor",
            "name": "Private Donor",
            "blood_group": "A+",
            "city": "Pune",
            "contact_phone": "+91 98765 12345",
        }, follow_redirects=True)
        self.assertIn(b"Consent is required", response.data)
        response = self.client.post("/blood-connect", data={
            "csrf_token": self.csrf(),
            "form_type": "donor",
            "name": "Private Donor",
            "blood_group": "A+",
            "city": "Pune",
            "contact_phone": "+91 98765 12345",
            "contact_consent": "yes",
        }, follow_redirects=True)
        self.assertIn(b"saved privately", response.data)
        self.assertNotIn(b"Private Donor", response.data)
        with get_db(self.database_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM donor_interests").fetchone()[0], 1)

    def test_existing_database_schema_and_seed_data_are_upgraded_idempotently(self):
        with get_db(self.database_path) as db:
            patient = db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Legacy Patient", "legacy@example.test", generate_password_hash("legacy password")),
            )
            db.execute(
                """INSERT INTO patient_profiles
                   (user_id, registration_number, mobile, age, area_city, privacy_consent)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (patient.lastrowid, "JSN-2026-LEGACY", "+919876543210", 35, "Nagpur"),
            )
            slot = db.execute(
                "SELECT id, doctor_id FROM doctor_slots ORDER BY slot_at LIMIT 1"
            ).fetchone()
            legacy_listing = db.execute(
                """INSERT INTO healthcare_directory
                   (name, category, address, city, source_url)
                   VALUES ('Legacy Preserved Hospital', 'hospital', 'Old address',
                           'Nagpur', 'https://legacy.example.test/')"""
            ).lastrowid
            db.execute("ALTER TABLE medical_reports DROP COLUMN language")
            db.execute("ALTER TABLE blood_requests DROP COLUMN status")
            db.execute("ALTER TABLE patient_otp_challenges DROP COLUMN consumed_at")
            db.execute("ALTER TABLE healthcare_directory DROP COLUMN ownership_type")
            db.execute(
                """CREATE TABLE appointments_legacy (
                    id INTEGER PRIMARY KEY,
                    patient_id INTEGER NOT NULL REFERENCES users(id),
                    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                    slot_id INTEGER NOT NULL REFERENCES doctor_slots(id),
                    status TEXT NOT NULL DEFAULT 'Pending',
                    visit_reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (patient_id, slot_id)
                )"""
            )
            db.commit()
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute(
                """INSERT INTO appointments_legacy (id, patient_id, doctor_id, slot_id, visit_reason)
                   VALUES (41, ?, ?, ?, 'legacy booking')""",
                (patient.lastrowid, slot["doctor_id"], slot["id"]),
            )
            db.execute("DROP TABLE appointments")
            db.execute("ALTER TABLE appointments_legacy RENAME TO appointments")
            db.execute(
                "INSERT INTO consultations (appointment_id, meeting_url, status) VALUES (41, '', 'Placeholder')"
            )
            db.commit()
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("DELETE FROM blood_banks")
        init_db(self.database_path, Path(self.app.root_path) / "schema.sql")
        with get_db(self.database_path) as db:
            report_columns = {row["name"] for row in db.execute("PRAGMA table_info(medical_reports)")}
            blood_columns = {row["name"] for row in db.execute("PRAGMA table_info(blood_requests)")}
            otp_columns = {row["name"] for row in db.execute("PRAGMA table_info(patient_otp_challenges)")}
            directory_columns = {row["name"] for row in db.execute("PRAGMA table_info(healthcare_directory)")}
            self.assertIn("language", report_columns)
            self.assertIn("status", blood_columns)
            self.assertIn("consumed_at", otp_columns)
            self.assertIn("ownership_type", directory_columns)
            preserved_listing = db.execute(
                "SELECT name, ownership_type FROM healthcare_directory WHERE id = ?",
                (legacy_listing,),
            ).fetchone()
            self.assertEqual(tuple(preserved_listing), ("Legacy Preserved Hospital", "unknown"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM blood_banks").fetchone()[0], 2)
            migrated_appointment = db.execute(
                "SELECT patient_id, visit_reason FROM appointments WHERE id = 41"
            ).fetchone()
            self.assertEqual(migrated_appointment["visit_reason"], "legacy booking")
            self.assertEqual(db.execute("SELECT appointment_id FROM consultations").fetchone()[0], 41)
            legacy_unique = False
            for index in db.execute("PRAGMA index_list(appointments)"):
                if index["unique"] and index["origin"] == "u":
                    columns = [
                        row["name"] for row in db.execute(f"PRAGMA index_info('{index['name']}')")
                    ]
                    legacy_unique = legacy_unique or columns == ["patient_id", "slot_id"]
            self.assertFalse(legacy_unique)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.client.get("/patient/access")
        code_response = self.client.post("/patient/access", data={
            "csrf_token": self.csrf(),
            "phase": "request",
            "mobile": "+919876543210",
        })
        code_match = re.search(
            rb"Local demo code:</strong>\s*<code>(\d{6})", code_response.data
        )
        self.assertIsNotNone(code_match)
        verified = self.client.post("/patient/access", data={
            "csrf_token": self.csrf(),
            "phase": "verify",
            "mobile": "+919876543210",
            "code": code_match.group(1).decode(),
        })
        self.assertEqual(verified.headers["Location"], "/patient/dashboard")
        with get_db(self.database_path) as db:
            self.assertIsNotNone(
                db.execute(
                    "SELECT consumed_at FROM patient_otp_challenges "
                    "WHERE mobile = ? AND consumed_at IS NOT NULL",
                    ("+919876543210",),
                ).fetchone()
            )

    def test_csrf_and_login_required_are_enforced(self):
        self.assertEqual(self.client.get("/appointments").status_code, 302)
        response = self.client.post("/login", data={"email": "nobody@example.test", "password": "bad"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
