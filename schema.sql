PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'patient' CHECK (role IN ('patient', 'doctor', 'hospital', 'admin')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hospitals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    opening_hours TEXT NOT NULL DEFAULT '',
    specialties TEXT NOT NULL DEFAULT '',
    latitude REAL,
    longitude REAL,
    verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    submitted_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id),
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    hospital_id INTEGER NOT NULL REFERENCES hospitals(id),
    experience_years INTEGER NOT NULL DEFAULT 0,
    consultation_mode TEXT NOT NULL DEFAULT 'In-person',
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1))
);

CREATE TABLE IF NOT EXISTS doctor_slots (
    id INTEGER PRIMARY KEY,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    slot_at TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    UNIQUE (doctor_id, slot_at)
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES users(id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    slot_id INTEGER NOT NULL REFERENCES doctor_slots(id),
    status TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Confirmed', 'Cancelled', 'Completed')),
    visit_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_slot
    ON appointments(slot_id) WHERE status IN ('Pending', 'Confirmed');

CREATE TABLE IF NOT EXISTS cancer_records (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    clinician_confirmed_info TEXT NOT NULL,
    treatment_name TEXT NOT NULL DEFAULT '',
    treatment_date TEXT NOT NULL,
    follow_up_date TEXT,
    clinician_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dialysis_schedules (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Upcoming' CHECK (status IN ('Upcoming', 'Completed', 'Missed')),
    clinician_name TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blood_requests (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    blood_group TEXT NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    hospital_location TEXT NOT NULL,
    city TEXT NOT NULL,
    urgency TEXT NOT NULL CHECK (urgency IN ('Routine', 'Urgent', 'Critical')),
    contact_name TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Resolved', 'Cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blood_banks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    opening_hours TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 1 CHECK (is_demo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS donor_interests (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    blood_group TEXT NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    city TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    consent INTEGER NOT NULL CHECK (consent IN (0, 1)),
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS medical_reports (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en' CHECK (language IN ('en', 'hi', 'mr')),
    extraction_status TEXT NOT NULL DEFAULT 'unreadable' CHECK (extraction_status IN ('readable', 'unreadable')),
    consent INTEGER NOT NULL CHECK (consent IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS report_findings (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES medical_reports(id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    result_value TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    reference_range TEXT NOT NULL DEFAULT '',
    flag TEXT NOT NULL DEFAULT 'Not assessed'
);

CREATE TABLE IF NOT EXISTS consultations (
    id INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL UNIQUE REFERENCES appointments(id) ON DELETE CASCADE,
    meeting_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Placeholder' CHECK (status IN ('Placeholder', 'Scheduled'))
);

CREATE TABLE IF NOT EXISTS consents (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    consented INTEGER NOT NULL CHECK (consented IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    read_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patient_profiles (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    registration_number TEXT NOT NULL UNIQUE,
    mobile TEXT NOT NULL UNIQUE,
    date_of_birth TEXT,
    age INTEGER,
    area_city TEXT NOT NULL,
    contact_email TEXT NOT NULL DEFAULT '',
    privacy_consent INTEGER NOT NULL CHECK (privacy_consent IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((date_of_birth IS NOT NULL AND age IS NULL) OR
           (date_of_birth IS NULL AND age IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS patient_otp_challenges (
    id INTEGER PRIMARY KEY,
    mobile TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT,
    provider TEXT NOT NULL DEFAULT 'demo'
        CHECK (provider IN ('demo', 'twilio')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'expired', 'failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS patient_otp_mobile_created
    ON patient_otp_challenges(mobile, created_at);

CREATE TABLE IF NOT EXISTS healthcare_directory (
    id INTEGER PRIMARY KEY,
    facility_id TEXT UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('cancer', 'dialysis', 'hospital', 'blood_bank', 'doctor')),
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    ownership_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (ownership_type IN ('government', 'private', 'unknown')),
    specialty TEXT NOT NULL DEFAULT '',
    services TEXT NOT NULL DEFAULT '',
    latitude REAL,
    longitude REAL,
    blood_stock TEXT NOT NULL DEFAULT '',
    opening_hours TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    last_verified TEXT,
    last_checked TEXT,
    notes TEXT NOT NULL DEFAULT '',
    source_verification_status TEXT NOT NULL DEFAULT '',
    potentially_duplicate INTEGER NOT NULL DEFAULT 0 CHECK (potentially_duplicate IN (0, 1)),
    verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('pending', 'verified', 'unverified')),
    last_updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_by INTEGER REFERENCES users(id),
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS healthcare_directory_search
    ON healthcare_directory(category, city, area, verification_status);

CREATE TABLE IF NOT EXISTS ayushman_empanelments (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES healthcare_directory(id) ON DELETE CASCADE,
    scheme_name TEXT NOT NULL CHECK (scheme_name IN ('PM-JAY', 'MJPJAY')),
    empanelment_verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (empanelment_verification_status IN ('pending', 'verified', 'unverified')),
    source_url TEXT NOT NULL,
    last_verified TEXT,
    specialties TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (listing_id, scheme_name),
    CHECK (
        empanelment_verification_status != 'verified'
        OR (last_verified IS NOT NULL AND length(trim(specialties)) > 0)
    )
);

CREATE INDEX IF NOT EXISTS ayushman_empanelments_verified
    ON ayushman_empanelments(scheme_name, empanelment_verification_status, listing_id);

CREATE TABLE IF NOT EXISTS directory_import_log (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
    records_read INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    flagged INTEGER NOT NULL DEFAULT 0,
    errors TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS provider_accounts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    listing_id INTEGER NOT NULL REFERENCES healthcare_directory(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS provider_slots (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES healthcare_directory(id) ON DELETE CASCADE,
    slot_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'closed')),
    published_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (listing_id, slot_at)
);

CREATE TABLE IF NOT EXISTS provider_appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES users(id),
    listing_id INTEGER NOT NULL REFERENCES healthcare_directory(id),
    slot_id INTEGER NOT NULL REFERENCES provider_slots(id),
    status TEXT NOT NULL DEFAULT 'Requested'
        CHECK (status IN ('Requested', 'Confirmed', 'Cancelled')),
    visit_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_provider_booking_per_slot
    ON provider_appointments(slot_id) WHERE status IN ('Requested', 'Confirmed');
