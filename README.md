# BGP-FRT-Report-Generator

A lightweight tool to generate an HTML5 report of a BGP Full Routing Table (FRT) using data collected via **pmacct / pmbgpd**.

The report provides a quick overview of:
- total prefixes
- IPv4 / IPv6 distribution
- announcements (self / customers)
- optional filtering (blackhole, mitigation, etc.)

Designed for ISPs and network operators who want a simple and customizable visibility tool. It works by this flow:

Route Reflector -> pmbgpd make json dump every 300 sec -> import-pmbgpd-rib.sh import of JSON into DB (and delete the old ones) -> generate_report.py use db to generate static HTML file

---

## ✨ Features

- HTML5 interactive report (no external dependencies)
- IPv4 / IPv6 breakdown
- Customer vs self announcements
- Configurable filtering (communities, blackhole, etc.)
- Multilingual-ready frontend (i18n support)
- Fully customizable via environment variables

---

## 📦 Requirements

- Python 3.8+
- PostgreSQL
- pmacct (with `pmbgpd`)
- Bash (for helper scripts)
- lsof
- jq

---

## 🚀 Setup

### 1. Clone Repo

Clone repo,  move to a specific folder and make executable every script

Example (Debian/Ubuntu):
```bash
cd /opt
git clone https://github.com/robynhub/BGP-FRT-Report-Generator.git
mv BGP-FRT-Report-Generator/ bgp-report
cd bgp-report
chmod +x *.sh *.py
```

---

### 2. Configure BGP session

Set up a BGP session between `pmbgpd` and your route reflector.

An example configuration is available in:

```
example/pmbgpd.conf
```

pick a folder to put BGP dumps. For example:

```
mkdir -p /var/spool/pmacct/
```

---

### 3. Setup PostgreSQL

Install PostgreSQL and create a database:

```bash
sudo -u postgres createdb bgp_report
```

Then import the schema:

```bash
mkdir -p /opt/bgp-report/schema
psql bgp_report < /opt/bgp-report/schema/schema.sql
```

---

### 4. Download AS-to-Organization database

Download and update the CAIDA AS2ORG dataset:

```bash
mkdir -p /opt/bgp-report/data
./opt/bgp-report/update-as2org.sh
```

Run this periodically (e.g. monthly via cron).

---

### 5. Configure scripts

Download and edit the following files:

- `/opt/bgp-report/import-pmbgpd-rib.sh`
- `/opt/bgp-report/generate_report.py`

Set:
- database credentials
- file paths
- ISP name
- optional filters (communities, etc.)

Or use the env file provided to set environment variables

---

### 6. Import BGP data

Download and Run the import script periodically to load RIB snapshots into PostgreSQL:

```bash
./opt/bgp-report/import-pmbgpd-rib.sh
```

Suggested: every 5–10 minutes via cron.

This script:
- processes JSON dumps from `pmbgpd`
- stores them in the database
- keeps only the latest snapshot
- RUN generate_report.py 

---

### 7. If you want to Generate only the report

Run:

```bash
python3 /opt/bgp-report/generate_report.py
```

The HTML report will be generated in the configured output directory.

---

## ⚙️ Configuration

The tool supports environment variables for customization.

Example (`.env`):

```bash
BGP_REPORT_ISP_NAME="MyISP"
BGP_REPORT_DB_HOST="localhost"
BGP_REPORT_DB_NAME="bgp_report"
BGP_REPORT_DB_USER="user"
BGP_REPORT_DB_PASSWORD="password"
```

---

## 🌍 Internationalization (i18n)

The frontend supports multiple languages.

- Default language is auto-detected from the browser
- Can be overridden via query string:

```
?lang=en
?lang=it
```

Translations are stored in:

```
/opt/bgp-report/i18n/
```

But needed to accessible via browser so:

```
cp -R /opt/bgp-report/i18n /var/www/html/
chown -R www-data:www-data /var/www/html/i18n
```

---

## 🧩 Customization

This tool is intentionally simple and meant to be adapted.

You can easily:
- change report layout
- add new metrics
- integrate with other data sources
- customize filtering logic

---

## 📁 Project Structure

```
.
├── example/                # Example pmbgpd config
├── schema/                 # PostgreSQL schema
├── i18n/                   # Translation files
├── generate_report.py      # Report generator
├── import-pmbgpd-rib.sh    # Data importer
├── update-as2org.sh        # AS2ORG updater
└── README.md
```

---

## 🤝 Contributing

Contributions, suggestions and improvements are welcome.

Feel free to:
- open issues
- submit pull requests
- fork and adapt to your needs


