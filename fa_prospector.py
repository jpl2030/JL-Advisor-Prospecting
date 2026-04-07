#!/usr/bin/env python3
"""
FA Prospector - Financial Advisor Acquisition Pipeline
Steward Partners | Central Florida Market
-------------------------------------------------------
Pulls registered advisors from BrokerCheck public API,
filters by registration date, geography, and firm type,
and outputs a clean PDF prospect list.

Usage:
    pip install requests reportlab
    python fa_prospector.py

Output:
    FA_Prospect_List_CentralFlorida.pdf
"""

import requests
import json
import time
import sys
from datetime import datetime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ─────────────────────────────────────────────
# CONFIGURATION — Edit these as needed
# ─────────────────────────────────────────────

# Central Florida zip codes (Orlando metro + surrounding)
CENTRAL_FLORIDA_ZIPS = [
    "32801", "32803", "32804", "32805", "32806", "32807", "32808",
    "32809", "32810", "32811", "32812", "32814", "32817", "32818",
    "32819", "32820", "32821", "32822", "32824", "32825", "32826",
    "32827", "32828", "32829", "32830", "32831", "32832", "32835",
    "32836", "32837", "32839",
    # Winter Park / Maitland / Altamonte
    "32789", "32792", "32751", "32701", "32714",
    # Lake Mary / Sanford
    "32746", "32771", "32773",
    # Kissimmee / St. Cloud
    "34741", "34743", "34744", "34746", "34769",
    # Clermont / Windermere / Ocoee
    "34711", "34714", "34715", "34786", "34787", "34761",
    # Daytona Beach area
    "32114", "32117", "32118", "32119",
    # Lakeland / Winter Haven
    "33801", "33803", "33805", "33809", "33813", "33880", "33884",
]

# Search radius in miles around each zip (keep low to avoid excessive overlap)
SEARCH_RADIUS = 10

# Cutoff: only include advisors registered before this year
# Pre-2000 = 25+ years in industry as of 2025
# Can be overridden via REG_YEAR_CUTOFF environment variable
import os as _os
REGISTRATION_YEAR_CUTOFF = int(_os.environ.get("REG_YEAR_CUTOFF", "2000"))

# Firms to EXCLUDE (hard to transition from, protocol non-signatories, etc.)
EXCLUDED_FIRMS = [
    "edward jones",
    "edward d. jones",
    "ameriprise",
    "northwestern mutual",
    "new york life",
    "massmutual",
    "mass mutual",
    "guardian life",
    "principal financial",
    "country financial",
    "primerica",
    "world financial group",
    "transamerica",
    "nationwide financial",
    "pacific life",
    "securian financial",
]

# Minimum results before we stop pagination per zip
MAX_RESULTS_PER_ZIP = 50

# Delay between API calls to be respectful (seconds)
API_DELAY = 0.5

# Output filename
OUTPUT_FILE = "FA_Prospect_List_CentralFlorida.pdf"

# ─────────────────────────────────────────────
# BROKERCHECK API
# ─────────────────────────────────────────────

BASE_URL = "https://api.brokercheck.finra.org/search/individual"

# Full browser-like headers to avoid being blocked by FINRA CDN/WAF
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://brokercheck.finra.org/",
    "Origin": "https://brokercheck.finra.org",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries on failure


def search_brokercheck(zip_code, start=0, rows=50):
    """Query BrokerCheck public API for individuals near a zip code."""
    params = {
        "query": "*",
        "zip": zip_code,
        "radius": SEARCH_RADIUS,
        "hl": "true",
        "includePrevious": "false",
        "wt": "json",
        "sort": "bc_lastname_sort+asc",
        "start": start,
        "rows": rows,
        "r": rows,
        "type": "individual",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                BASE_URL, params=params, headers=HEADERS,
                timeout=20, allow_redirects=True
            )
            if resp.status_code != 200:
                print(f"    [!] HTTP {resp.status_code} for zip {zip_code} "
                      f"(attempt {attempt}): {resp.text[:200]}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return None
            print(f"\n=== RAW TEXT (zip {zip_code}) ===")
            print(resp.text[:1000])
            print("=== END ===\n")
            data = resp.json()            
            # DEBUG — print raw response for first call only
            import os as _os2
            if _os2.environ.get("DEBUG_FIRST_CALL") == "1":
                import json as _json2
                print("\n=== RAW API RESPONSE ===")
                print(_json2.dumps(data, indent=2)[:3000])
                print("=== END RAW RESPONSE ===\n")
                _os2.environ["DEBUG_FIRST_CALL"] = "0"
            if "hits" not in data:
                print(f"    [!] Unexpected response for zip {zip_code}: "
                      f"{str(data)[:200]}")
                return None
            return data
        except requests.exceptions.RequestException as e:
            print(f"    [!] Request error for zip {zip_code} "
                  f"(attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    return None


def get_individual_detail(ind_crd):
    """Fetch detailed record for a specific CRD number."""
    url = f"https://api.brokercheck.finra.org/search/individual/{ind_crd}"
    params = {"hl": "true", "includePrevious": "true", "wt": "json"}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException:
        return None


def parse_registration_year(date_str):
    """Extract year from a date string like '01/1998' or '1998-01-01'."""
    if not date_str:
        return None
    for fmt in ("%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).year
        except ValueError:
            continue
    # Last resort: grab first 4 digits that look like a year
    import re
    match = re.search(r"(19[5-9]\d|20[0-2]\d)", date_str)
    if match:
        return int(match.group(1))
    return None


def firm_excluded(firm_name):
    """Return True if the firm is on the exclusion list."""
    if not firm_name:
        return False
    lower = firm_name.lower()
    return any(excl in lower for excl in EXCLUDED_FIRMS)


# ─────────────────────────────────────────────
# DATA COLLECTION
# ─────────────────────────────────────────────

def collect_prospects():
    """Pull and filter advisors across all Central Florida zip codes."""
    seen_crds = set()
    all_prospects = []
    total_zips = len(CENTRAL_FLORIDA_ZIPS)

    print(f"\n{'='*60}")
    print(f"  FA PROSPECTOR — Central Florida")
    print(f"  Registration cutoff: before {REGISTRATION_YEAR_CUTOFF}")
    print(f"  Searching {total_zips} zip codes...")
    print(f"{'='*60}\n")

    for idx, zip_code in enumerate(CENTRAL_FLORIDA_ZIPS, 1):
        print(f"[{idx:>3}/{total_zips}] Zip {zip_code}...", end="", flush=True)

        data = search_brokercheck(zip_code, start=0, rows=MAX_RESULTS_PER_ZIP)
        if not data:
            print(" skip (error)")
            continue

        try:
            hits = data.get("hits", {}).get("hits", [])
            total_found = data.get("hits", {}).get("total", 0)
        except (AttributeError, KeyError):
            print(" skip (parse error)")
            continue

        # DEBUG — print first zip's raw response so we can see field names
        if idx == 1 and hits:
            import json as _json
            print("\n=== DEBUG SAMPLE (first result) ===")
            print(_json.dumps(hits[0].get("_source", {}), indent=2)[:2000])
            print("=== END DEBUG ===\n")

        new_count = 0
        for hit in hits:
            src = hit.get("_source", {})
            ind_crd = src.get("ind_source_id") or hit.get("_id", "")

            if not ind_crd or ind_crd in seen_crds:
                continue
            seen_crds.add(ind_crd)

            # --- Basic fields from search result ---
            first = src.get("ind_firstname", "").strip()
            last = src.get("ind_lastname", "").strip()
            full_name = f"{first} {last}".strip() or "Unknown"

            firm = src.get("ind_bc_employer", "") or src.get("ind_employed_by", "")
            if isinstance(firm, list):
                firm = firm[0] if firm else ""
            firm = firm.strip()

            # Exclude undesirable firms immediately
            if firm_excluded(firm):
                continue

            # Registration date
            reg_date_raw = (
                src.get("ind_bc_registration_bgn_dt")
                or src.get("ind_registration_date")
                or src.get("ind_bc_current_employer_registration_bgn_dt")
                or ""
            )
            reg_year = parse_registration_year(reg_date_raw)

            # Filter: only advisors registered before cutoff year
            if reg_year and reg_year >= REGISTRATION_YEAR_CUTOFF:
                continue

            # --- Collect remaining fields ---
            state = src.get("ind_bc_address_state", "FL")
            city = src.get("ind_bc_address_city", "").strip().title()
            zip_val = src.get("ind_bc_address_zip5", zip_code)
            has_disclosures = src.get("ind_has_complaints", False) or src.get("ind_bc_disclosures_fl", False)
            disclosures_count = src.get("ind_num_bc_complaints", 0)
            licenses_raw = src.get("ind_licenses", [])
            if isinstance(licenses_raw, list):
                licenses = ", ".join(licenses_raw) if licenses_raw else "N/A"
            else:
                licenses = str(licenses_raw)

            broker_url = f"https://brokercheck.finra.org/individual/summary/{ind_crd}"

            prospect = {
                "name": full_name,
                "first": first,
                "last": last,
                "crd": ind_crd,
                "firm": firm or "Unknown",
                "city": city,
                "state": state,
                "zip": zip_val,
                "reg_year": reg_year,
                "reg_date_raw": reg_date_raw,
                "years_in_industry": (datetime.now().year - reg_year) if reg_year else None,
                "has_disclosures": has_disclosures,
                "disclosures_count": disclosures_count,
                "licenses": licenses,
                "brokercheck_url": broker_url,
                "phone": "",        # To be filled manually
                "email": "",        # To be filled manually
                "linkedin": "",     # To be filled manually
                "notes": "",        # To be filled manually
            }
            all_prospects.append(prospect)
            new_count += 1

        time.sleep(API_DELAY)
        print(f" {new_count} new prospects (total={len(all_prospects)})")

    # Sort: earliest registration first (most senior advisors at top)
    all_prospects.sort(key=lambda x: x.get("reg_year") or 9999)

    print(f"\n✅ Collection complete. Total prospects: {len(all_prospects)}")
    return all_prospects


# ─────────────────────────────────────────────
# PDF GENERATION
# ─────────────────────────────────────────────

def build_pdf(prospects, output_path):
    """Generate a clean, professional prospect list PDF."""

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(letter),
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ProspectTitle",
        parent=styles["Title"],
        fontSize=20,
        textColor=colors.HexColor("#1a2e4a"),
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#4a6080"),
        spaceAfter=2,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#1a2e4a"),
        spaceBefore=14,
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=7.5,
        textColor=colors.HexColor("#333333"),
        leading=10,
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
    )
    url_style = ParagraphStyle(
        "URL",
        parent=styles["Normal"],
        fontSize=7,
        textColor=colors.HexColor("#1a6fb5"),
        leading=10,
    )

    story = []
    now_str = datetime.now().strftime("%B %d, %Y")
    year_now = datetime.now().year

    # ── Cover / Header ──
    story.append(Paragraph("Steward Partners — FA Acquisition Prospect List", title_style))
    story.append(Paragraph(f"Central Florida Market  |  Generated: {now_str}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a2e4a"), spaceAfter=8))

    # ── Summary Stats ──
    reg_years = [p["reg_year"] for p in prospects if p["reg_year"]]
    firms_seen = {}
    for p in prospects:
        firms_seen[p["firm"]] = firms_seen.get(p["firm"], 0) + 1
    top_firms = sorted(firms_seen.items(), key=lambda x: -x[1])[:5]

    avg_tenure = round(sum(year_now - y for y in reg_years) / len(reg_years), 1) if reg_years else 0
    pre_1990 = sum(1 for y in reg_years if y < 1990)

    summary_data = [
        ["Total Prospects", "Avg. Years in Industry", "Registered Pre-1990", "Zip Codes Searched", "Cutoff Year"],
        [
            str(len(prospects)),
            f"{avg_tenure} yrs",
            str(pre_1990),
            str(len(CENTRAL_FLORIDA_ZIPS)),
            f"Before {REGISTRATION_YEAR_CUTOFF}",
        ],
    ]
    summary_table = Table(summary_data, colWidths=[1.8 * inch] * 5)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2e4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#eef2f7")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 13),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#1a2e4a")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#1a2e4a"), colors.HexColor("#eef2f7")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1a2e4a")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#aabbcc")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # ── Top Firms ──
    if top_firms:
        firm_text = "  |  ".join([f"{f[0]} ({f[1]})" for f in top_firms])
        story.append(Paragraph(f"<b>Top firms represented:</b>  {firm_text}", small_style))

    story.append(Spacer(1, 6))

    exclusion_text = (
        "<b>Excluded firms:</b>  " +
        ", ".join(e.title() for e in EXCLUDED_FIRMS[:8]) +
        (" + more" if len(EXCLUDED_FIRMS) > 8 else "")
    )
    story.append(Paragraph(exclusion_text, small_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<i>Fields marked [FILL] should be completed manually via LinkedIn, firm website, or cold outreach.</i>",
        small_style
    ))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aabbcc"), spaceAfter=8))

    # ── Prospect Table ──
    story.append(Paragraph("Prospect Directory", section_style))

    # Table header
    col_widths = [
        1.6 * inch,   # Name
        1.5 * inch,   # Firm
        0.9 * inch,   # City
        0.65 * inch,  # Reg. Year
        0.65 * inch,  # Yrs
        0.55 * inch,  # Discl.
        1.1 * inch,   # Licenses
        1.3 * inch,   # Phone [FILL]
        1.4 * inch,   # Email [FILL]
        1.4 * inch,   # LinkedIn [FILL]
        1.3 * inch,   # Notes
    ]

    header_row = [
        Paragraph("<b>Name / CRD</b>", small_style),
        Paragraph("<b>Current Firm</b>", small_style),
        Paragraph("<b>City</b>", small_style),
        Paragraph("<b>Reg. Year</b>", small_style),
        Paragraph("<b>Yrs In</b>", small_style),
        Paragraph("<b>Discl.</b>", small_style),
        Paragraph("<b>Licenses</b>", small_style),
        Paragraph("<b>Phone [FILL]</b>", small_style),
        Paragraph("<b>Email [FILL]</b>", small_style),
        Paragraph("<b>LinkedIn [FILL]</b>", small_style),
        Paragraph("<b>Notes</b>", small_style),
    ]

    table_data = [header_row]

    row_colors = [colors.HexColor("#d4e0ef"), colors.white]

    for i, p in enumerate(prospects):
        reg_display = str(p["reg_year"]) if p["reg_year"] else "Unknown"
        yrs_display = str(p["years_in_industry"]) if p["years_in_industry"] else "?"
        discl_display = f"Yes ({p['disclosures_count']})" if p["has_disclosures"] else "No"
        discl_color = colors.HexColor("#cc3300") if p["has_disclosures"] else colors.HexColor("#006633")

        name_para = Paragraph(
            f"<b>{p['name']}</b><br/><font size='6.5' color='#666666'>CRD: {p['crd']}</font>",
            cell_style,
        )
        crd_link = Paragraph(
            f"<a href='{p['brokercheck_url']}' color='#1a6fb5'>BrokerCheck ↗</a>",
            url_style,
        )

        row = [
            [name_para, crd_link],
            Paragraph(p["firm"], cell_style),
            Paragraph(p["city"] or "FL", cell_style),
            Paragraph(reg_display, cell_style),
            Paragraph(yrs_display, cell_style),
            Paragraph(discl_display, ParagraphStyle("Discl", parent=cell_style,
                                                     textColor=discl_color, fontName="Helvetica-Bold", fontSize=8)),
            Paragraph(p["licenses"][:40] + ("..." if len(p["licenses"]) > 40 else ""), cell_style),
            Paragraph("", cell_style),  # Phone FILL
            Paragraph("", cell_style),  # Email FILL
            Paragraph("", cell_style),  # LinkedIn FILL
            Paragraph("", cell_style),  # Notes
        ]
        table_data.append(row)

    prospect_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Alternating row colors
    row_bg_cmds = []
    for i in range(1, len(table_data)):
        bg = colors.HexColor("#f0f5fa") if i % 2 == 0 else colors.white
        row_bg_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))

    prospect_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2e4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        # Grid
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#aabbcc")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        *row_bg_cmds,
    ]))
    story.append(prospect_table)

    # ── Appendix: Firms Breakdown ──
    story.append(PageBreak())
    story.append(Paragraph("Appendix A — Firm Breakdown", section_style))
    story.append(Paragraph(
        "Distribution of prospects across current firms. Use this to prioritize outreach by firm cluster.",
        small_style
    ))
    story.append(Spacer(1, 8))

    all_firms_sorted = sorted(firms_seen.items(), key=lambda x: -x[1])
    firm_table_data = [
        [Paragraph("<b>Firm</b>", small_style),
         Paragraph("<b>Count</b>", small_style),
         Paragraph("<b>Transition Notes</b>", small_style)]
    ]

    transition_notes = {
        "raymond james": "Protocol signatory — standard transition process",
        "wells fargo": "Protocol signatory — standard process; large platform",
        "ubs": "Protocol signatory — often smooth transitions",
        "merrill lynch": "Protocol signatory — complex but common",
        "morgan stanley": "Protocol signatory — strong brand, aggressive retention",
        "lpl financial": "Independent — generally favorable to transitions",
        "commonwealth": "Independent — advisor-friendly",
        "ameritas": "Non-protocol — consult legal before approach",
        "stifel": "Protocol signatory",
        "janney": "Protocol signatory",
    }

    for firm_name, count in all_firms_sorted:
        note = ""
        for key, val in transition_notes.items():
            if key in firm_name.lower():
                note = val
                break
        if not note:
            note = "Research transition terms before approach"

        firm_table_data.append([
            Paragraph(firm_name, cell_style),
            Paragraph(str(count), cell_style),
            Paragraph(note, cell_style),
        ])

    firm_table = Table(firm_table_data, colWidths=[3.5 * inch, 0.8 * inch, 5.5 * inch])
    firm_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2e4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#aabbcc")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f5fa")]),
    ]))
    story.append(firm_table)

    # ── Appendix: Outreach Strategy ──
    story.append(PageBreak())
    story.append(Paragraph("Appendix B — 6-Month Outreach Strategy", section_style))

    strategy_text = """
<b>Month 1-2 — Research & Warm Prep</b><br/>
Fill in missing phone numbers and emails using LinkedIn, firm directories, and tools like Hunter.io or Apollo.io (fits your $50-200 budget).
Prioritize advisors registered pre-1990 — these are your highest-probability acquisition targets (35+ years in industry, likely succession planning).<br/><br/>

<b>Month 2-3 — Initial Outreach</b><br/>
Lead with LinkedIn connection requests and a personalized note referencing their tenure. Do NOT pitch acquisition immediately.
Subject line approach: "Fellow advisor in [City] — quick intro" or "Steward Partners — expanding in Central FL."
Goal at this stage: schedule a 20-min call, not a deal.<br/><br/>

<b>Month 3-4 — Relationship Cultivation</b><br/>
Phone follow-ups to prospects who connected on LinkedIn. Focus on understanding their succession situation.
Key qualifying questions: Are they thinking about the next 5-10 years? Do they have a transition plan? Are they open to conversations about options?<br/><br/>

<b>Month 4-5 — Qualification & Pitch</b><br/>
For prospects who are open, introduce Steward Partners' model — independence with institutional support, buyout structures, transition packages.
Bring in your senior team / principal for any serious conversations.<br/><br/>

<b>Month 5-6 — Follow-Up & Pipeline Management</b><br/>
Track all contacts in a CRM (even a simple spreadsheet). Categorize: Hot / Warm / Long-Term.
Not every advisor will be ready now — the ones who aren't are still worth staying in contact with quarterly.<br/><br/>

<b>Supplemental Tools (within your $50-200 budget)</b><br/>
• Apollo.io — email + phone enrichment (~$50/mo starter plan)<br/>
• Hunter.io — email finder by firm domain<br/>
• LinkedIn Sales Navigator — most powerful for this use case (~$99/mo, best ROI if you can swing it)<br/>
• Lusha Chrome extension — pull contact info from LinkedIn profiles (~$39/mo)<br/>
"""
    story.append(Paragraph(strategy_text, ParagraphStyle(
        "Strategy", parent=styles["Normal"], fontSize=9, leading=14,
        textColor=colors.HexColor("#222222")
    )))

    # ── Footer note ──
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aabbcc")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<i>Generated {now_str} | Source: FINRA BrokerCheck public data | "
        f"For internal Steward Partners use only | "
        f"All data is publicly available per FINRA BrokerCheck Terms of Use.</i>",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                       textColor=colors.HexColor("#888888"), alignment=TA_CENTER)
    ))

    # Build PDF
    doc.build(story)
    print(f"\n📄 PDF saved: {output_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("\n🔍 Starting FA Prospector...")
    print(f"   Target: Central Florida")
    print(f"   Filtering: Registered before {REGISTRATION_YEAR_CUTOFF}")
    print(f"   Excluding: {len(EXCLUDED_FIRMS)} firm types\n")

    # Collect data
    prospects = collect_prospects()

    if not prospects:
        print("\n⚠️  No prospects found. Possible causes:")
        print("   - BrokerCheck API blocking GitHub runner IPs (most likely)")
        print("   - All results filtered out by current cutoff settings")
        print("   - Network connectivity issues")
        print("\n   Writing empty-result PDF so the pipeline does not crash...")
        # Build a notice PDF so send_report.py still has something to attach
        from reportlab.pdfgen import canvas as _canvas
        from reportlab.lib.pagesizes import letter as _letter
        _c = _canvas.Canvas(OUTPUT_FILE, pagesize=_letter)
        _c.setFont("Helvetica-Bold", 14)
        _c.drawCentredString(306, 500, "FA Prospector — No Results This Run")
        _c.setFont("Helvetica", 11)
        _c.drawCentredString(306, 470, "BrokerCheck API may have blocked the request.")
        _c.drawCentredString(306, 450, "Try triggering a manual run in a few hours,")
        _c.drawCentredString(306, 430, "or increase REG_YEAR_CUTOFF to 2005 or 2010.")
        _c.save()
        print(f"   Wrote notice PDF: {OUTPUT_FILE}")
        # Exit 0 so the email step still runs and you get notified
        sys.exit(0)

    print(f"\n📊 Building PDF with {len(prospects)} prospects...")
    build_pdf(prospects, OUTPUT_FILE)

    print(f"\n✅ Done! Open {OUTPUT_FILE} to view your prospect list.")
    print(f"   Next step: Fill in Phone / Email / LinkedIn columns using Apollo.io or Hunter.io")


if __name__ == "__main__":
    main()
