# JeevanSetu AI

A student-friendly healthcare coordination demo built with **HTML, CSS, JavaScript, Flask, and SQLite**. It brings care directories, category-specific patient registration, appointment requests, cancer and dialysis tracking, blood requests, and private report uploads into one local application.

> **Important:** This is a hackathon/student demo, not a medical device or production healthcare service. Demo clinicians, time slots, and blood requests are fictional. Facility directory entries are sourced from the supplied workbook but may be incomplete or unverified. Nothing here confirms current appointments, services, blood inventory, scheme eligibility, coverage, clinical advice, or emergency support. Never delay emergency care for this website or a video consultation.

## Features in this demo

- A unified, responsive home dashboard with directory search, emergency assistance, connected service shortcuts, patient-specific upcoming appointments, and source-labelled Nagpur facility highlights.
- A refreshed, mobile-first application shell with a role-aware desktop sidebar, compact header, five-item mobile navigation, unified care dashboard, accessible focus states, responsive service cards, and reduced-motion support. The assistant-language selector remembers English, Hindi, or Marathi for AI chat; other page copy is currently English.
- A private patient dashboard at `/patient/dashboard` with editable name/area/contact email, real appointment counts and history, upcoming appointments, care summaries, and shortcuts to existing patient services. The mobile number and registration number remain read-only in this demo; a mobile identity change would require a verification flow not provided here.
- An Ayushman Bharat information page with official PM-JAY beneficiary and Maharashtra MJPJAY links, helpline 14555, and filters that show only separately verified scheme-participation and relevant-specialty records.
- Source-attributed healthcare directory for facilities imported from the supplied Nagpur workbook. Search covers facility name, address, area/city, contact, service, and specialty; filters include category, specialty/service, location, and government/private ownership only when explicitly included in an authorized import. Existing rows without ownership evidence are shown as "Not supplied" and are not guessed. Results can be sorted by name, area, or update date. Listings retain their source wording and are shown as verified, unverified, or pending; community submissions remain hidden until an administrator verifies them.
- Fictional doctor profiles, sample slots, appointment booking, cancellation, rescheduling, and status tracking. Database constraints prevent an active slot from being booked twice.
- Verified provider-published slots and their associated hospital/department or doctor/specialty are selected together as a request; the UI does not claim independently confirmed real-time availability. Patient and provider-request cancellation is owner-scoped, and appointment history/statuses appear on the dashboard.
- A video-consultation information page. No video service is integrated; an HTTPS meeting link can be configured for local demonstration.
- Patient-owned cancer-care timeline for information the patient says was clinician-confirmed, and a private dialysis schedule tracker. Neither feature diagnoses or changes treatment.
- Blood requests and donor-interest forms, group/city filters, and a fictional blood-bank directory. Patients can privately mark their requests open, resolved, or cancelled; this status is user-managed and does not confirm blood availability. Contact information is not publicly displayed.
- Private Medical Reports page uploads for PDFs/images (8 MB limit), best-effort text extraction from text-based PDFs, and English/Hindi/Marathi explanations. That page does not OCR images. The demo explanation reports only values/ranges it can parse and does not diagnose or infer cancer stage.
- A site-wide floating JeevanSetu AI chat and a dedicated `/ai-assistant` page. Chat uses the OpenAI Python SDK when configured, supports English/Hindi/Marathi and health-information topics, and uses existing SQLite directory records for hospital searches. Without an API key, chat reports that configuration is missing rather than inventing an answer.
- Optional, explicit-consent report explanation in chat for readable text PDFs and validated PNG/JPEG images. Images are sent as images to a vision-capable OpenAI model; scanned PDFs are unsupported. Files are type/size checked and processed in memory.
- Optional OpenAI-compatible AI API configuration. Report text is sent externally **only** when the user checks the separate external-processing consent box. Without the configured API, the local demo mode does not send report text anywhere.
- Hashed passwords, patient-only self-registration, staff roles, CSRF protection on forms, parameterized SQL, private report downloads, and owner-scoped records.
- Installable PWA metadata with 192px and 512px PNG app icons, an Apple touch icon, browser install prompt where supported, and a service worker that caches static UI assets only. It never caches private pages, API responses, or medical records; when offline it shows a generic reconnect page. Hospital search, account workflows, AI, and uploads still require a live connection.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- Visual Studio Code (recommended)

## Run locally on Windows

1. Install Python from [python.org](https://www.python.org/downloads/) and VS Code if they are not already installed. During Python setup, enable **Add Python to PATH**.
2. Open this project folder in VS Code (`File > Open Folder`).
3. Open the integrated terminal (**Terminal > New Terminal**) and create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

4. Activate it in PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell does not allow script activation, open a Command Prompt terminal and use:

   ```bat
   .venv\Scripts\activate.bat
   ```

5. Install the project dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

6. Start the Flask application:

   ```powershell
   python -m flask --app app run
   ```

   The SQLite database and private upload directory are created automatically under `instance\` on first run. Flask prints its local address.

7. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

Register to create a patient account. There is no shared demo password or pre-created user account. Public facility directory pages are available without signing in; doctor/demo scheduling samples are not verified real-world providers or slots.

### Install on a phone

Run the application on `localhost` (or deploy it behind HTTPS); browsers do not allow PWA installation from an ordinary insecure network address. On a supported Android browser, open the site and use the **Install app** button if the browser offers installation, or use its browser menu. On iPhone/iPad, use Safari's **Share → Add to Home Screen**. The install prompt is browser-controlled and may not appear until the browser's installability criteria are met. The service worker caches only static assets and a generic offline notice; the website's private data and live features are not available offline. Native-only capabilities such as push notifications or emergency calling integrations are not included.

### Nagpur healthcare directory and workbook import

Open the home page at [http://127.0.0.1:5000](http://127.0.0.1:5000) and choose `/cancer-facilities`, `/dialysis-facilities`, or `/blood-banks`. Each directory is category-specific, searchable, and links back to Home. The broader directory remains at `/hospitals`. Listings display source and verification details where supplied. Workbook blood-stock fields are source notes, **not live availability**; call the facility to confirm services, hours, and availability.

Patient registration is available from each category page. The category is saved with the patient profile; care-related information is optional and requires separate consent. The confirmation page displays the registration ID only in the authenticated session and states that no appointment or treatment was booked. Returning-patient records remain protected by mobile verification. Twilio Verify is the default SMS mode and requires the server-side settings described below; local demo mode is optional and never sends SMS. Existing dashboards are available at `/patient/dashboard`.

The provided `Nagpur_Healthcare_Structured_Database.xlsx` is in the project root. Its Facility Directory contains 28 non-header rows: 27 facility records are retained and one lookup/instruction row is skipped. Data Analysis is displayed as workbook statistics; Add New Records Template is available for future submissions at `/directory/template`. These records do not establish complete Nagpur coverage or independent official verification.

To re-import from the command line after installing dependencies:

```powershell
python -m flask --app app import-healthcare-workbook
```

For a new local database, run this batch import once before starting the server to load the supplied 27 source-attributed Nagpur facility records. It is safe to repeat; later runs report unchanged rows unless the source workbook has changed.

To import an authorized `.xlsx`, `.csv`, or `.json` export through the authenticated administrator interface, first create an admin account using `create-staff`, sign in, and open [http://127.0.0.1:5000/admin/import](http://127.0.0.1:5000/admin/import). The interface previews additions, changes, unchanged rows, and potential duplicates before committing. Imports preserve source metadata, never delete absent records, and log success or failure. Exact re-imports are idempotent. Same-name, category, and city records with different addresses are flagged for review rather than merged.

The repeatable parser/importer is in `data_import.py`. The Excel sheet is the only currently configured data source; no government, e-RaktKosh, SMS, or hospital API has been configured. Additional facilities require a reliable authorized export/API and appropriate verification before being marked verified.

The public Smart Hospital Finder is `/directory` (also available as `/hospitals`). Search accepts name, address, area/city, phone, website, service, or specialty terms. Specialty/service, category, city, area, ownership (government/private), and result sorting filters are supported. Ownership is only classified when supplied in authorized source data; omitted/legacy values remain unknown. CSV/JSON imports can provide `ownership_type` as `government`, `private`, or `unknown`; structured workbooks may include an optional `Facility Type` column. Re-imports that omit that optional field preserve an existing ownership value. Facility detail pages include a call action only for a valid phone number and a map link only when a usable address or coordinates exist.

After patient registration/mobile verification, `/patient/dashboard` summarizes that patient's own doctor appointments and provider appointment requests, upcoming counts, completion/cancellation counts, selected care summaries, and service shortcuts. Patients may edit their name, area/city, and contact email there; mobile and registration number are not editable without a real verification process. The dashboard does not include saved/recently viewed facilities because that feature is not implemented.

### Ayushman Bharat information (Nagpur)

Open `/ayushman-bharat` from the navigation without signing in. The page links to the official [PM-JAY beneficiary portal](https://beneficiary.nha.gov.in/) and [Maharashtra MJPJAY website](https://www.jeevandayee.gov.in/), and displays helpline **14555**. It filters scheme, cancer/oncology, dialysis/kidney care, hospital name, and area, but displays a hospital only when both the hospital directory record and its PM-JAY/MJPJAY empanelment record are marked verified, and the verified scheme specialty matches the selected care filter.

The supplied Nagpur workbook has no PM-JAY/MJPJAY empanelment field or scheme-specific proof. Its hospital and specialty records are therefore **not** shown as scheme-empanelled. The new optional importer columns are `scheme_name`, `empanelment_verification_status`, `scheme_source_url`, `scheme_last_verified`, and `scheme_specialties` for CSV/JSON; workbooks may include corresponding `Scheme Name`, `Empanelment Verification Status`, `Scheme Source URL`, `Scheme Last Verified`, and `Scheme Specialties` columns. Scheme source links must be HTTPS on `.gov.in` or `.nic.in`; claiming a record is verified also requires a verification date and specialties. This format validation does not itself establish truth: only enter verified status after checking reliable official scheme evidence. Existing hospital rows remain unempanelled unless separately documented this way.

Patients should confirm eligibility, covered procedures, authorization, and current hospital participation directly with the official scheme or hospital. No cashless treatment is promised. JeevanSetu AI does not determine eligibility and must not be used to submit Ayushman cards, Aadhaar, or government identity numbers. Patient registration is separate from government scheme eligibility.

### Administrator and staff accounts

Patient accounts can only be created through patient registration. To create an administrator, doctor, or hospital staff account, stop the Flask server and run:

```powershell
python -m flask --app app create-staff
```

Follow the prompts; the password is hidden rather than passed on the command line. For a doctor account, link a doctor profile ID when prompted. The profile IDs are in the local `doctors` table (the fictional seeded profiles are IDs 1–3 on a fresh database). Only appointments assigned to that linked profile are visible to the doctor account. For a hospital account, an administrator can first review and verify the provider's pending directory listing, then create the account and link its verified listing ID when prompted. A listing can be linked to only one hospital account; a blank ID creates an account without listing access. Admin linking is a demo workflow and does not independently verify hospital credentials.

### Patient SMS verification (Twilio Verify)

The default `SMS_OTP_MODE=twilio` requires a configured Twilio Verify service. The server normalizes Indian mobile numbers to `+91XXXXXXXXXX`, stores only a hash of its local challenge token, limits requests to five per number per 15 minutes, enforces a 60-second resend cooldown, expires challenges after five minutes, and limits verification attempts to five. Twilio Verify performs the real code check; the app grants dashboard access only after Twilio returns `approved` and the verified number belongs to a registered patient. Responses do not confirm whether a number is registered. A provider request response is not proof of carrier delivery, so the page does not claim that an SMS was delivered.

To configure real SMS:

1. Create a Twilio account and complete any account, billing, identity, and destination setup Twilio requires for sending SMS to India.
2. In Twilio Console, create a **Verify Service**. The app enforces a five-minute local challenge expiry even if the provider's own code validity is longer; check the provider's current token-validity options and defaults.
3. Copy `.env.example` to `.env` in the project root and privately fill in `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and the Verify Service SID (`VA...`). Keep `SMS_OTP_MODE=twilio`. `.env` is ignored by Git; never paste secrets into source code, commit them, or send them in logs/screenshots.
4. Stop and restart Flask after editing `.env`. Without all three credentials, requests fail safely and no SMS is sent.

Twilio may require account upgrades, billing, regulatory/sender configuration, and destination permissions before India delivery. Automated tests use mocked Twilio calls and never make paid requests. Real delivery has not been verified by this project; confirm delivery to your own test phone and check Twilio's delivery status in its console.

For local-only testing without provider credentials, set `SMS_OTP_MODE=demo` in `.env` and restart Flask. A random code is displayed in the browser for any valid Indian number; **no SMS is sent**. A demo code cannot open a dashboard unless the number matches an existing registration. Never use demo mode or real patient information in production.

### AI Health Assistant (OpenAI)

The shared navigation and floating chat are available without patient login. Visit `/ai-assistant` for the full-page interface. The assistant sends chat messages to OpenAI using the official Python SDK; hospital searches add matching non-duplicate SQLite directory records and their source/verification metadata to the request. It does not provide diagnosis, cancer stage, prescriptions, emergency triage, real-time hospital availability, or blood stock. A report is only sent after selecting the report topic and explicitly checking the consent box. Avoid entering identifying information. Readable PDF text is extracted in memory; PNG/JPEG images are validated and sent to OpenAI's vision-capable chat model. Scanned PDFs are not supported. Use a vision-capable model (the default `gpt-4o-mini` supports image input).

To enable actual model responses, obtain an OpenAI API key and create a local `.env` file in the project root (this file is already ignored by Git):

```powershell
@'
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
'@ | Set-Content -Encoding ascii .env
```

Replace the placeholder with your key; never commit or share `.env`. `OPENAI_MODEL` is optional and defaults to `gpt-4o-mini`. Restart Flask after changing `.env`. Without a valid key/network/model, the chat displays a configuration/provider error and does not return a demo or fabricated AI answer. The test suite uses a mocked SDK response and does not require an API key; a real model response requires your own key and was not verified by the tests.

The older report-upload explanation setting below (`AI_API_URL`, `AI_MODEL`, `AI_API_KEY`) is separate from chat and configures the existing report page's optional OpenAI-compatible endpoint. Do not confuse it with the chat's `OPENAI_API_KEY`/`OPENAI_MODEL`.

### Optional report-page AI and video configuration

The app never includes API keys in source code. In the same PowerShell terminal where Flask will run, configure an HTTPS OpenAI-compatible chat-completions endpoint, model, and key:

```powershell
$env:AI_API_URL = "https://your-provider.example/v1/chat/completions"
$env:AI_MODEL = "your-model-name"
$env:AI_API_KEY = Read-Host "AI API key"
python -m flask --app app run
```

Use the endpoint and model provided by your chosen service. Keep the key in a secret manager or environment variable; do not commit it or put it in a checked-in `.env` file. These variables are per terminal session. External report processing is optional and requires a separate checkbox for each upload. Do not send real patient information to an AI provider unless you have the appropriate authorization and the provider's privacy terms permit it. If configuration is missing, the app uses its local demo explanation without sending report data.

To show an existing HTTPS video meeting link for eligible demo appointments, set `VIDEO_MEETING_URL` in the terminal before starting Flask. This only displays the configured link; it does not create or verify a real consultation.

For a stable local session secret, optionally set `JEEVANSETU_SECRET_KEY` to a long random secret in your terminal before launch. The app generates a random key automatically for a quick local run; sessions will reset when that process restarts. The development server is not intended for deployment to the public internet.

## Run tests

Activate the virtual environment and run:

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary SQLite databases and upload folders. They cover page rendering and directory search, workbook parsing and repeatable import, scheme-source validation and verified-only Ayushman filters, update and duplicate handling, patient registration, demo mobile-code access, mocked Twilio request/approval/failure, phone normalization, verification attempt and resend limits, registration privacy and account isolation, password hashing and redirect validation, hospital verification and provider-account linking, provider-published appointment requests and account-scoped status updates, appointment collisions/cancellation/rescheduling and doctor permissions, cancer/dialysis and blood-request persistence, donor privacy, report ownership/consent/type/size checks, PDF extraction and unreadable-report behavior, AI assistant page/API configuration, mocked OpenAI SDK responses, directory context, report consent, image validation and no-storage behavior, CSRF enforcement, and upgrades of an existing database.

## Project structure

```text
app.py                 Flask routes, validation, authentication, and OpenAI-backed assistant
database.py            SQLite connection and fictional demo-data setup
schema.sql             Related database tables, constraints, and indexes
requirements.txt       Flask, PDF/Excel/image support, OpenAI and Twilio SDKs, and dotenv dependencies
.env.example           Blank Twilio Verify configuration template; copy to ignored .env
data_import.py         Validated CSV/JSON/Excel parsing, preview, and transactional directory import logic
Nagpur_Healthcare_Structured_Database.xlsx  Supplied source workbook and future-entry template
templates/             Jinja-rendered HTML pages
static/css/style.css   Responsive design system and assistant widget
static/js/app.js       Mobile navigation and asynchronous assistant chat
static/manifest.webmanifest  Installable PWA metadata
static/sw.js           Static-asset cache and generic offline fallback only
static/icons/           Application SVG icon
tests/                 Basic Flask application tests
instance/              Generated SQLite database and private report uploads (git-ignored)
```

## Demo limitations and safety

- No real hospital booking, doctor scheduling, blood-stock feed, or video provider is integrated. Twilio Verify is implemented but requires a user's own configured account/service; actual SMS delivery is not verified by this project. Local demo verification displays a code and never sends SMS.
- The Nagpur directory is an initial sourced workbook import, not an exhaustive district directory. Workbook content has not been independently verified by this application; confirm details directly with facilities. Additional directory data needs authorized sources, attribution, and administrator verification.
- The administrator's verification is a demo listing-review workflow, not an external credential check.
- Existing SQLite databases are upgraded in place at startup when the report-language or blood-request-status fields, blood-bank directory, or active-booking constraint are missing; existing appointment records are preserved.
- The doctor directory is seeded with fictional entries; a staff account must be explicitly linked to a profile before it can see that profile's appointments.
- The Medical Reports page does not OCR images or scanned PDFs. The chat assistant can send a consented PNG/JPEG image to OpenAI's vision-capable model; scanned PDFs remain unsupported. Unreadable files are rejected instead of fabricated.
- The chat assistant requires an OpenAI API key for actual responses. Automated tests mock the provider; no live AI call is made by the test suite. Chat accepts readable text-based PDFs and validated PNG/JPEG images; scanned PDF extraction and OCR are not provided.
- Report comparisons use only simple numeric ranges recognized in the report text. They are not clinical interpretations and may miss complex formats.
- The optional external AI service is unverified by this project. Its output can be wrong; it is informational and must be reviewed by a qualified healthcare professional.
- SQLite report text and files are protected by application ownership checks, but are not encrypted at rest by this demo. Use only fictional or appropriately authorized test data. A real service would need a formal privacy/security review, encryption/key management, audit controls, consent governance, backups, and provider integrations.
