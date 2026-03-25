# BGP-FRT-Report-Generator
A tool that generate a simple HTML5 report of BGP Full Routing Table gathered with pmbgpd.
Feel free do adapt to your needs

  # How to use
  Step 1) Install pmacct suite
  Step 2) Setup a BGP session with your route reflector using the config file for pmbgpd in example dir
  Step 3) Install PostgreSQL and create a new db with the sql file in schema/ dir
  Step 4) Download and update-as2org.sh once a month and download the latest as2org database
  Step 5) Downdoad and edit import-pmbgpd-rib.sh and generate_report.py files.
  Step 6) Run every 10 minutes or so the script import-pmbgpd-rib.sh that put all the json dump made by pmbgpd into the db (only one copy kept)
  Step 7) Profit

