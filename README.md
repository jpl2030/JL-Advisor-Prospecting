# FA Prospector — Central Florida

Automated pipeline that pulls senior financial advisors from FINRA BrokerCheck,
filters by geography, tenure, firm type, and compliance record, and delivers a
PDF prospect list to your inbox on the 1st of every month.

Built for Steward Partners FA acquisition strategy.

---

## What it does

1. Searches 50+ Central Florida zip codes via the BrokerCheck public API
2. Filters for advisors registered before 2000 (25+ years in industry)
3. Excludes hard-to-transition firms (Edward Jones, Ameriprise, NWM, etc.)
4. Removes anyone with active regulatory disclosures
5. Outputs a PDF with a prospect table + firm breakdown + 6-month outreach strategy
6. Emails the PDF to you automatically via Gmail

---

## Repo structure

```
fa-prospector/
├── .github/
│   └── workflows/
│       └── run_prospector.yml   # GitHub Actions schedule
├── fa_prospector.py             # Main data collection + PDF generation
├── send_report.py               # Gmail delivery
├── requirements.txt
└── README.md
```

---

## One-time setup

### Step 1 — Create a new GitHub repo

1. Go to github.com and click **New repository**
2. Name it `fa-prospector` (private recommended)
3. Do NOT initialize with a README (you'll push this code directly)

### Step 2 — Push this code to GitHub

On your machine, open a terminal in the folder containing these files and run:

```bash
git init
git add .
git commit -m "Initial FA prospector pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/fa-prospector.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

### Step 3 — Set up a Gmail App Password

The pipeline sends email via Gmail using an App Password (not your regular password).

1. Go to myaccount.google.com
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google," enable **2-Step Verification** if not already on
4. Search for **App passwords** in the search bar at the top
5. Create a new app password — name it "FA Prospector"
6. Copy the 16-character password that appears — you will not see it again

### Step 4 — Add GitHub Secrets

These keep your credentials out of the code entirely.

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** and add each of the following:

| Secret name | Value |
|---|---|
| `GMAIL_USER` | Your Gmail address (e.g. jacob@gmail.com) |
| `GMAIL_APP_PASSWORD` | The 16-character app password from Step 3 |
| `RECIPIENT_EMAIL` | Where to send the report (can be same as GMAIL_USER) |

### Step 5 — Test it manually

1. In your repo, go to the **Actions** tab
2. Click **FA Prospector — Monthly Run** in the left sidebar
3. Click **Run workflow** → **Run workflow**
4. Watch the run complete (takes 5–15 minutes depending on API response times)
5. Check your inbox for the PDF

---

## Customization

### Change the registration year cutoff

The default filters for advisors registered before 2000. To broaden the list,
trigger a manual run and enter a different year (e.g. `2005` for 20+ year veterans).

Or edit the default in `fa_prospector.py`:
```python
REGISTRATION_YEAR_CUTOFF = int(_os.environ.get("REG_YEAR_CUTOFF", "2000"))
```

### Add or remove excluded firms

Edit the `EXCLUDED_FIRMS` list in `fa_prospector.py`. Strings are matched
case-insensitively and partially (so "edward jones" catches "Edward D. Jones & Co.").

### Change the run schedule

Edit the cron expression in `.github/workflows/run_prospector.yml`:
```yaml
- cron: "0 12 1 * *"   # 7 AM ET on the 1st of every month
```
Cron syntax: minute / hour (UTC) / day-of-month / month / day-of-week

---

## Filling in contact details

The PDF has blank Phone, Email, and LinkedIn columns. Recommended tools:

- **Apollo.io** (~$50/mo) — paste name + firm, bulk-enriches contact data
- **Hunter.io** — finds emails by firm domain
- **Lusha** Chrome extension (~$39/mo) — pulls contact info from LinkedIn profiles
- **LinkedIn Sales Navigator** (~$99/mo) — most powerful if budget allows

---

## Notes

- All data comes from FINRA BrokerCheck public records — no login required
- This pipeline does not store or transmit any advisor PII beyond your own inbox
- Review BrokerCheck Terms of Use at brokercheck.finra.org before use
- The PDF artifact is also saved in GitHub Actions for 90 days as a backup
