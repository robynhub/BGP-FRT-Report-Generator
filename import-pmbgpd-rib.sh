#!/bin/bash
set -euo pipefail


DBNAME="bgpmon"
DBUSER="bgpmon"
export PGPASSWORD='bgpmon'
DBHOST="127.0.0.1"
DUMPDIR="/var/spool/pmacct"



is_file_open_by_pmbgpd() {
  local file="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof "$file" 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx 'pmbgpd'
    return $?
  fi

  return 1
}

is_file_stable() {
  local file="$1"
  local wait_secs="${2:-3}"

  [ -f "$file" ] || return 1

  local size1 mtime1 size2 mtime2 now age
  size1=$(stat -c %s "$file") || return 1
  mtime1=$(stat -c %Y "$file") || return 1
  now=$(date +%s)
  age=$((now - mtime1))


  [ "$age" -ge 5 ] || return 1

  sleep "$wait_secs"

  [ -f "$file" ] || return 1
  size2=$(stat -c %s "$file") || return 1
  mtime2=$(stat -c %Y "$file") || return 1

  [ "$size1" -eq "$size2" ] && [ "$mtime1" -eq "$mtime2" ]
}

select_latest_stable_dump() {
  local dumpdir="$1"
  local f

  for f in $(ls -1t "${dumpdir}"/bgp-table-*.json 2>/dev/null); do
    [ -f "$f" ] || continue

    if is_file_open_by_pmbgpd "$f"; then
      continue
    fi

    if is_file_stable "$f" 3; then
      echo "$f"
      return 0
    fi
  done

  return 1
}

LATEST="$(select_latest_stable_dump "$DUMPDIR" || true)"

if [ -z "${LATEST}" ]; then
  echo "No dump found"
  exit 1
fi

echo Using file ${LATEST}


psql -v ON_ERROR_STOP=1 -h "$DBHOST" -U "$DBUSER" -d "$DBNAME" -c "TRUNCATE rib_stage;"

jq -r '
  def n: "";
  select(has("ip_prefix")) |
  [
    (.peer_ip_src // n),
    (.afi // n),
    (.safi // n),
    (.ip_prefix // n),
    (.bgp_nexthop // n),
    (.as_path // n),
    n,
    (.comms // n),
    (.local_pref // n),
    (.med // n),
    (.origin // n)
  ] | @tsv
' "$LATEST" | psql -v ON_ERROR_STOP=1 -h "$DBHOST" -U "$DBUSER" -d "$DBNAME" -c "\copy rib_stage(peer_ip, afi, safi, prefix, next_hop, as_path, origin_as, communities, local_pref, med, origin) FROM STDIN WITH (FORMAT text)"

psql -v ON_ERROR_STOP=1 -h "$DBHOST" -U "$DBUSER" -d "$DBNAME" <<'SQL'
INSERT INTO current_rib (
    peer_ip, afi, safi, prefix, next_hop, as_path, origin_as,
    communities, local_pref, med, origin, last_seen
)
SELECT
    NULLIF(peer_ip, '')::inet,
    NULLIF(afi, '')::smallint,
    NULLIF(safi, '')::smallint,
    NULLIF(prefix, '')::inet,
    NULLIF(NULLIF(btrim(trim(next_hop), '"'), ''), 'null')::inet,
    NULLIF(as_path, ''),
    CASE
      WHEN NULLIF(trim(as_path), '') IS NULL THEN NULL
      ELSE (regexp_match(
        trim(as_path),
        '([0-9]+)(?:[[:space:]]+\{[^}]+\})?$'
      ))[1]::bigint
    END,
    NULLIF(communities, ''),
    NULLIF(local_pref, '')::integer,
    NULLIF(med, '')::integer,
    NULLIF(origin, ''),
    now()
FROM rib_stage
ON CONFLICT (peer_ip, afi, safi, prefix)
DO UPDATE SET
    next_hop    = EXCLUDED.next_hop,
    as_path     = EXCLUDED.as_path,
    origin_as   = EXCLUDED.origin_as,
    communities = EXCLUDED.communities,
    local_pref  = EXCLUDED.local_pref,
    med         = EXCLUDED.med,
    origin      = EXCLUDED.origin,
    last_seen   = now();

DELETE FROM current_rib c
WHERE c.peer_ip = '109.73.81.1'::inet
  AND NOT EXISTS (
    SELECT 1
    FROM rib_stage s
    WHERE NULLIF(s.peer_ip, '')::inet = c.peer_ip
      AND NULLIF(s.afi, '')::smallint = c.afi
      AND NULLIF(s.safi, '')::smallint = c.safi
      AND NULLIF(s.prefix, '')::inet = c.prefix
  );
SQL

LATEST="$(select_latest_stable_dump "$DUMPDIR" || true)"
find "$DUMPDIR" -maxdepth 1 -type f -name 'bgp-table-*.json' ! -samefile "$LATEST" -delete

/opt/bgp-report/generate_report.py
chown www-data:www-data /var/www/html/frt-report.html

echo "Import completed. Only file kept: $LATEST"
