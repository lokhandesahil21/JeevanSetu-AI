import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from data_import import (
    DirectoryImportError,
    import_directory_records,
    parse_healthcare_workbook,
    preview_directory_import,
)
from database import get_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_PATH = PROJECT_ROOT / "Nagpur_Healthcare_Structured_Database.xlsx"


class HealthcareWorkbookImportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE": str(self.database_path),
            "UPLOAD_FOLDER": str(Path(self.temp_dir.name) / "uploads"),
        })
        self.workbook = parse_healthcare_workbook(WORKBOOK_PATH.read_bytes())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_workbook_sheets_and_records_are_parsed_without_template_rows(self):
        self.assertEqual(self.workbook["records_read"], 28)
        self.assertEqual(len(self.workbook["records"]), 27)
        self.assertEqual(self.workbook["skipped"], 1)
        self.assertTrue(self.workbook["analysis"])
        self.assertTrue(self.workbook["template_headers"])
        self.assertTrue(all(row["name"] for row in self.workbook["records"]))

    def test_workbook_import_command_loads_and_repeatably_updates_the_directory(self):
        runner = self.app.test_cli_runner()
        first = runner.invoke(args=["import-healthcare-workbook"])
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertIn("imported 27", first.output)
        second = runner.invoke(args=["import-healthcare-workbook"])
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertIn("unchanged 27", second.output)
        with get_db(self.database_path) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM healthcare_directory WHERE facility_id LIKE 'xlsx-%'"
            ).fetchone()[0]
        self.assertEqual(count, 27)

    def test_import_and_reimport_are_idempotent_and_preserve_attribution(self):
        with get_db(self.database_path) as db:
            first = import_directory_records(db, self.workbook["records"])
            db.commit()
            second = import_directory_records(db, self.workbook["records"])
            db.commit()
            self.assertEqual(first["inserted"], 27)
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(second["unchanged"], 27)
            row = db.execute(
                "SELECT source_url, source_verification_status, verification_status "
                "FROM healthcare_directory WHERE facility_id = ?",
                (self.workbook["records"][0]["facility_id"],),
            ).fetchone()
            self.assertIsNotNone(row["source_url"])
            self.assertIsNotNone(row["source_verification_status"])
            self.assertIn(row["verification_status"], ("pending", "unverified", "verified"))

    def test_ownership_type_is_optional_and_validated_for_searchable_imports(self):
        source = dict(
            self.workbook["records"][0],
            facility_id="ownership-test-001",
            name="Ownership Test Hospital",
            category="hospital",
            address="10 Sourced Road",
            ownership_type="Government",
            verification_status="unverified",
        )
        with get_db(self.database_path) as db:
            result = import_directory_records(db, [source])
            db.commit()
            stored = db.execute(
                "SELECT ownership_type FROM healthcare_directory WHERE facility_id = ?",
                ("ownership-test-001",),
            ).fetchone()
            self.assertEqual(result["inserted"], 1)
            self.assertEqual(stored["ownership_type"], "government")

            legacy_source = dict(source, ownership_type="")
            import_directory_records(db, [legacy_source])
            preserved = db.execute(
                "SELECT ownership_type FROM healthcare_directory WHERE facility_id = ?",
                ("ownership-test-001",),
            ).fetchone()
            self.assertEqual(preserved["ownership_type"], "government")

            invalid = dict(source, facility_id="ownership-test-invalid", ownership_type="nonprofit")
            with self.assertRaises(DirectoryImportError):
                preview_directory_import(db, [invalid])

    def test_scheme_import_requires_official_source_and_tracks_scheme_changes(self):
        record = dict(
            next(row for row in self.workbook["records"] if row["category"] == "cancer"),
            verification_status="verified",
            last_verified="2026-10-10",
            scheme_name="PM-JAY",
            empanelment_verification_status="verified",
            scheme_source_url="https://www.jeevandayee.gov.in/",
            scheme_last_verified="2026-10-10",
            scheme_specialties="Medical oncology",
        )
        with get_db(self.database_path) as db:
            result = import_directory_records(db, [record])
            db.commit()
            self.assertEqual(result["inserted"], 1)
            listing = db.execute(
                "SELECT id FROM healthcare_directory WHERE facility_id = ?",
                (record["facility_id"],),
            ).fetchone()
            scheme = db.execute(
                "SELECT * FROM ayushman_empanelments WHERE listing_id = ?",
                (listing["id"],),
            ).fetchone()
            self.assertEqual(scheme["scheme_name"], "PM-JAY")
            self.assertEqual(scheme["specialties"], "Medical oncology")
            self.assertEqual(preview_directory_import(db, [record])["unchanged"], 1)

            changed = dict(record, scheme_specialties="Medical oncology, radiotherapy")
            self.assertEqual(preview_directory_import(db, [changed])["updated"], 1)
            import_directory_records(db, [changed])
            db.commit()
            self.assertEqual(
                db.execute(
                    "SELECT specialties FROM ayushman_empanelments WHERE listing_id = ?",
                    (listing["id"],),
                ).fetchone()["specialties"],
                "Medical oncology, radiotherapy",
            )

        invalid = dict(record, scheme_source_url="https://example.com/hospitals")
        with get_db(self.database_path) as db:
            with self.assertRaises(DirectoryImportError):
                preview_directory_import(db, [invalid])
        invalid = dict(record, scheme_specialties="")
        with get_db(self.database_path) as db:
            with self.assertRaises(DirectoryImportError):
                preview_directory_import(db, [invalid])

    def test_existing_record_updates_and_invalid_coordinates_are_rejected(self):
        record = dict(self.workbook["records"][0])
        with get_db(self.database_path) as db:
            import_directory_records(db, [record])
            changed = dict(record, phone="+91 70000 00000")
            preview = preview_directory_import(db, [changed])
            self.assertEqual(preview["updated"], 1)
            result = import_directory_records(db, [changed])
            db.commit()
            self.assertEqual(result["updated"], 1)
            self.assertEqual(
                db.execute(
                    "SELECT phone FROM healthcare_directory WHERE facility_id = ?",
                    (record["facility_id"],),
                ).fetchone()["phone"],
                "+91 70000 00000",
            )
            invalid = dict(changed, latitude=100)
            with self.assertRaises(DirectoryImportError):
                preview_directory_import(db, [invalid])

    def test_duplicate_rows_are_not_inserted_and_branch_conflicts_are_flagged(self):
        record = dict(self.workbook["records"][0])
        with get_db(self.database_path) as db:
            duplicate_result = import_directory_records(db, [record, dict(record)])
            self.assertEqual(duplicate_result["inserted"], 1)
            self.assertEqual(duplicate_result["unchanged"], 1)

            branch = dict(
                record,
                facility_id="xlsx-test-distinct-branch",
                address=record["address"] + ", Other Branch",
            )
            result = import_directory_records(db, [branch])
            db.commit()
            self.assertEqual(result["flagged"], 1)
            inserted = db.execute(
                "SELECT verification_status, potentially_duplicate "
                "FROM healthcare_directory WHERE facility_id = ?",
                (branch["facility_id"],),
            ).fetchone()
            self.assertEqual(inserted["verification_status"], "pending")
            self.assertEqual(inserted["potentially_duplicate"], 1)

    def test_directory_search_persists_and_import_page_requires_admin(self):
        record = self.workbook["records"][0]
        with get_db(self.database_path) as db:
            import_directory_records(db, [record])
            db.commit()
        restarted_app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE": str(self.database_path),
            "UPLOAD_FOLDER": str(Path(self.temp_dir.name) / "uploads"),
        })
        client = restarted_app.test_client()
        self.assertEqual(client.get("/admin/import").status_code, 302)
        client.get("/login")
        with get_db(self.database_path) as db:
            db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                ("Test Admin", "admin@example.test", generate_password_hash("admin-password")),
            )
        client.get("/login")
        with client.session_transaction() as client_session:
            csrf_token = client_session["csrf_token"]
        client.post("/login", data={
            "csrf_token": csrf_token,
            "email": "admin@example.test",
            "password": "admin-password",
        })
        self.assertEqual(client.get("/admin/import").status_code, 200)
        response = client.get("/hospitals", query_string={"q": record["name"]})
        self.assertEqual(response.status_code, 200)
        self.assertIn(record["name"].encode(), response.data)
        self.assertIn(record["source_url"].encode(), response.data)

    def test_landing_and_category_directories_are_separate_and_searchable(self):
        with get_db(self.database_path) as db:
            import_directory_records(db, self.workbook["records"])
            db.commit()
        client = self.app.test_client()
        home = client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.data.count(b'class="service-tile '), 6)
        self.assertIn(b'id="app-sidebar"', home.data)
        self.assertIn(b'id="assistant-language"', home.data)
        self.assertIn(b"Ayushman Bharat", home.data)

        category_paths = {
            "cancer": "/cancer-facilities",
            "dialysis": "/dialysis-facilities",
            "blood_bank": "/blood-banks",
        }
        for category, path in category_paths.items():
            records = [row for row in self.workbook["records"] if row["category"] == category]
            self.assertTrue(records)
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(records[0]["name"].encode(), response.data)
            other_records = [
                row for row in self.workbook["records"]
                if row["category"] != category
            ]
            self.assertNotIn(other_records[0]["name"].encode(), response.data)
            self.assertIn(b"Patient Registration", response.data)
            self.assertIn(b"Back to Home", response.data)

        selected = next(row for row in self.workbook["records"] if row["category"] == "cancer")
        filtered = client.get(
            "/cancer-facilities",
            query_string={"q": selected["name"], "area": "Nagpur"},
        )
        self.assertIn(selected["name"].encode(), filtered.data)
        self.assertNotIn(b"Dialysis Facilities", filtered.data)

        blood_bank = next(row for row in self.workbook["records"] if row["category"] == "blood_bank")
        blood_page = client.get("/blood-banks", query_string={"q": blood_bank["name"]})
        self.assertIn(blood_bank["name"].encode(), blood_page.data)
        self.assertIn(b"Not independently verified as current inventory", blood_page.data)
        self.assertIn(b"not live availability", blood_page.data)

    def test_ayushman_page_only_lists_fully_verified_matching_scheme_records(self):
        client = self.app.test_client()
        page = client.get("/ayushman-bharat")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"https://beneficiary.nha.gov.in/", page.data)
        self.assertIn(b"https://www.jeevandayee.gov.in/", page.data)
        self.assertIn(b"tel:14555", page.data)
        self.assertIn(b"Do not upload an Ayushman card or Aadhaar", page.data)
        self.assertNotIn(b'name="aadhaar"', page.data.lower())
        self.assertNotIn(b'name="ayushman_card"', page.data.lower())
        self.assertIn(b"No verified matches are currently listed", page.data)

        cancer_record = dict(
            next(row for row in self.workbook["records"] if row["category"] == "cancer"),
            verification_status="verified",
            last_verified="2026-10-10",
            scheme_name="PM-JAY",
            empanelment_verification_status="verified",
            scheme_source_url="https://www.jeevandayee.gov.in/",
            scheme_last_verified="2026-10-10",
            scheme_specialties="Medical oncology, radiotherapy",
        )
        dialysis_record = dict(
            next(row for row in self.workbook["records"] if row["category"] == "dialysis"),
            verification_status="verified",
            last_verified="2026-10-10",
            scheme_name="MJPJAY",
            empanelment_verification_status="verified",
            scheme_source_url="https://www.jeevandayee.gov.in/",
            scheme_last_verified="2026-10-10",
            scheme_specialties="Nephrology, dialysis",
        )
        with get_db(self.database_path) as db:
            import_directory_records(db, [cancer_record, dialysis_record])
            db.commit()

        cancer_page = client.get("/ayushman-bharat?scheme=PM-JAY&care=cancer")
        self.assertIn(cancer_record["name"].encode(), cancer_page.data)
        self.assertNotIn(dialysis_record["name"].encode(), cancer_page.data)
        kidney_page = client.get("/ayushman-bharat?care=dialysis&area=impossible")
        self.assertNotIn(dialysis_record["name"].encode(), kidney_page.data)
        dialysis_area = dialysis_record["address"].split(",")[0]
        area_page = client.get(
            "/ayushman-bharat",
            query_string={
                "scheme": "MJPJAY",
                "care": "dialysis",
                "name": dialysis_record["name"],
                "area": dialysis_area,
            },
        )
        self.assertIn(dialysis_record["name"].encode(), area_page.data)

    def test_registration_stores_selected_category_and_shows_private_confirmation(self):
        endpoints = {
            "cancer": b"/cancer-facilities",
            "dialysis": b"/dialysis-facilities",
            "blood_bank": b"/blood-banks",
        }
        for index, (category, directory_path) in enumerate(endpoints.items()):
            with self.subTest(category=category):
                client = self.app.test_client()
                self.assertEqual(client.get("/patient/registration-confirmation").status_code, 302)
                registration_page = client.get(f"/patient/register?category={category}")
                self.assertIn(f'value="{category}" selected'.encode(), registration_page.data)
                with client.session_transaction() as client_session:
                    csrf_token = client_session["csrf_token"]
                mobile = f"+9198765432{index:02d}"
                care_info = "Follow-up requested" if category == "dialysis" else ""
                response = client.post("/patient/register", data={
                    "csrf_token": csrf_token,
                    "name": f"Test Patient {category}",
                    "mobile": mobile,
                    "age": "35",
                    "area_city": "Nagpur",
                    "care_category": category,
                    "care_information": care_info,
                    "care_information_consent": "yes" if care_info else "",
                    "privacy_consent": "yes",
                })
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/patient/registration-confirmation")
                confirmation = client.get("/patient/registration-confirmation")
                self.assertEqual(confirmation.status_code, 200)
                self.assertIn(b"Registration complete", confirmation.data)
                self.assertIn(b"No appointment or treatment was booked", confirmation.data)
                self.assertIn(directory_path, confirmation.data)
                with get_db(self.database_path) as db:
                    profile = db.execute(
                        "SELECT registration_number, care_category, care_information "
                        "FROM patient_profiles WHERE mobile = ?",
                        (mobile,),
                    ).fetchone()
                self.assertTrue(profile["registration_number"].startswith("JSN-"))
                self.assertEqual(profile["care_category"], category)
                self.assertEqual(profile["care_information"], care_info)
