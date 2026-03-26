#!/usr/bin/env python3

import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone

import psycopg2
from jinja2 import Template


# Runtime configuration via environment variables.
DB_NAME = os.getenv("BGP_REPORT_DB_NAME", "bgpmon")
DB_USER = os.getenv("BGP_REPORT_DB_USER", "bgpmon")
DB_PASSWORD = os.getenv("BGP_REPORT_DB_PASSWORD", "bgpmon")
DB_HOST = os.getenv("BGP_REPORT_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("BGP_REPORT_DB_PORT", "5432"))

OUTPUT_HTML = os.getenv("BGP_REPORT_OUTPUT_HTML", "/var/www/html/frt-report.html")
REPORT_TITLE = os.getenv("BGP_REPORT_TITLE", "FRT Report")
ISP_NAME = os.getenv("BGP_REPORT_ISP_NAME", "Your ISP")
PEER_IP = os.getenv("BGP_REPORT_PEER_IP", "127.0.0.1")

COMMUNITY_SELF = os.getenv("BGP_REPORT_COMMUNITY_SELF", "65000:10")
COMMUNITY_CUSTOMERS = os.getenv("BGP_REPORT_COMMUNITY_CUSTOMERS", "65000:100")
BH_RE = re.compile(os.getenv("BGP_REPORT_BLACKHOLE_REGEX", r'^65000:\d9\d\d$'))
MITIGATION_RE = re.compile(os.getenv("BGP_REPORT_MITIGATION_REGEX", r'^65000:666\d$'))

AS2ORG_FILE = os.getenv("BGP_REPORT_AS2ORG_FILE", "/opt/bgp-report/data/as2org.txt")
I18N_DIR = os.getenv("BGP_REPORT_I18N_DIR", "./i18n")
DEFAULT_LANG = os.getenv("BGP_REPORT_DEFAULT_LANG", "en")
SUPPORTED_LANGS = [
    lang.strip() for lang in os.getenv("BGP_REPORT_SUPPORTED_LANGS", "en,it").split(",") if lang.strip()
]

TOP_N_COMMUNITIES = int(os.getenv("BGP_REPORT_TOP_N_COMMUNITIES", "12"))
TOP_N_HOPS = int(os.getenv("BGP_REPORT_TOP_N_HOPS", "8"))
TOP_N_ORIGIN_AS = int(os.getenv("BGP_REPORT_TOP_N_ORIGIN_AS", "12"))
TOP_N_NEXT_HOPS = int(os.getenv("BGP_REPORT_TOP_N_NEXT_HOPS", "12"))


HTML_TEMPLATE = r"""<!doctype html>
<html lang="{{ default_lang }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #111827;
      --panel-2: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --border: #374151;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.4;
    }
    header {
      padding: 24px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
    }
    h1, h2, h3 { margin: 0 0 12px 0; }
    .subtitle { color: var(--muted); margin-top: 6px; }
    .container {
      max-width: 1800px;
      margin: 0 auto;
      padding: 20px;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 6px 24px rgba(0,0,0,.15);
    }
    .metric {
      font-size: 2rem;
      font-weight: 700;
      margin-top: 8px;
    }
    .metric-label {
      color: var(--muted);
      font-size: 0.95rem;
    }
    .grid-2 {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(520px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }
    .grid-4 {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }
    .grid-1 {
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      margin-bottom: 20px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
    }
    .panel h2 {
      font-size: 1.1rem;
      margin-bottom: 14px;
    }
    canvas {
      width: 100% !important;
      max-height: 420px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
      word-break: break-word;
    }
    th, td {
      border-bottom: 1px solid var(--border);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      background: rgba(255,255,255,0.02);
      position: sticky;
      top: 0;
    }
    .table-wrap {
      overflow: auto;
      max-height: 520px;
    }
    .tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--panel-2);
      border: 1px solid var(--border);
      color: var(--text);
      font-size: 0.8rem;
      margin-right: 6px;
      margin-bottom: 6px;
    }
    .small {
      color: var(--muted);
      font-size: 0.9rem;
    }
    .section-space {
      margin-top: 12px;
    }
    .chart-wrap {
      max-width: 520px;
      margin: 0 auto;
    }
    .chart-wrap.chart-wrap-wide {
      max-width: 1000px;
    }
    .chart-wrap.chart-wrap-tall canvas {
      max-height: 840px;
      min-height: 840px;
    }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .lang-switcher {
      margin-top: 10px;
    }
    .lang-switcher select {
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 6px 10px;
    }
    footer {
      color: var(--muted);
      border-top: 1px solid var(--border);
      margin-top: 24px;
      padding: 20px 0;
    }
  </style>
</head>
<body>
<header>
  <div class="container">
    <h1 data-i18n="report.title">{{ title }}</h1>
    <div class="subtitle">
      <span data-i18n="report.generated_at">Generated at</span>:
      <span class="mono" id="generated-at" data-generated-at="{{ generated_at_iso }}">{{ generated_at }}</span>
      <span class="mono" id="generated-ago"></span> ·
      <span data-i18n="report.total_routes">Total routes</span>:
      <span class="mono">{{ total_routes }}</span>
    </div>
    <div class="lang-switcher">
      <label for="lang-select" data-i18n="report.language">Language</label>
      <select id="lang-select"></select>
    </div>
  </div>
</header>

<div class="container">
  <div class="cards">
    <div class="card">
      <div class="metric-label" data-i18n="cards.ipv4_routes">IPv4 routes</div>
      <div class="metric">{{ ipv4_count }}</div>
    </div>
    <div class="card">
      <div class="metric-label" data-i18n="cards.ipv6_routes">IPv6 routes</div>
      <div class="metric">{{ ipv6_count }}</div>
    </div>
    <div class="card">
      <div class="metric-label" data-i18n="cards.avg_path_with_prepend">Average AS-PATH with prepend</div>
      <div class="metric">{{ avg_path_with_prepend }}</div>
    </div>
    <div class="card">
      <div class="metric-label" data-i18n="cards.avg_path_without_prepend">Average AS-PATH without prepend</div>
      <div class="metric">{{ avg_path_without_prepend }}</div>
    </div>
    <div class="card">
      <div class="metric-label" data-i18n="cards.routes_with_prepend">Routes with prepend</div>
      <div class="metric">{{ routes_with_prepend }}</div>
    </div>
    <div class="card">
      <div class="metric-label" data-i18n="cards.self_announcements">Self-originated announcements</div>
      <div class="metric">{{ self_count }}</div>
    </div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h2 data-i18n="charts.current_route_count">Current number of IPv4 / IPv6 routes</h2>
      <canvas id="pieRoutes"></canvas>
    </div>
    <div class="panel">
      <h2 data-i18n="charts.prefix_length_distribution">IPv4 / IPv6 prefix length distribution</h2>
      <canvas id="barPrefixLen"></canvas>
    </div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h2 data-i18n="charts.path_with_prepend">AS-PATH length with prepend</h2>
      <canvas id="histWithPrepend"></canvas>
      <div class="small section-space">
        <span data-i18n="stats.ipv4_average">IPv4 average</span> {{ avg_v4_with_prepend }},
        <span data-i18n="stats.median">median</span> {{ med_v4_with_prepend }},
        <span data-i18n="stats.p95">p95</span> {{ p95_v4_with_prepend }} ·
        <span data-i18n="stats.ipv6_average">IPv6 average</span> {{ avg_v6_with_prepend }},
        <span data-i18n="stats.median">median</span> {{ med_v6_with_prepend }},
        <span data-i18n="stats.p95">p95</span> {{ p95_v6_with_prepend }}
      </div>
    </div>
    <div class="panel">
      <h2 data-i18n="charts.path_without_prepend">AS-PATH length without prepend</h2>
      <canvas id="histWithoutPrepend"></canvas>
      <div class="small section-space">
        <span data-i18n="stats.ipv4_average">IPv4 average</span> {{ avg_v4_without_prepend }},
        <span data-i18n="stats.median">median</span> {{ med_v4_without_prepend }},
        <span data-i18n="stats.p95">p95</span> {{ p95_v4_without_prepend }} ·
        <span data-i18n="stats.ipv6_average">IPv6 average</span> {{ avg_v6_without_prepend }},
        <span data-i18n="stats.median">median</span> {{ med_v6_without_prepend }},
        <span data-i18n="stats.p95">p95</span> {{ p95_v6_without_prepend }}
      </div>
    </div>
  </div>

  <div class="grid-1">
    <div class="panel">
      <h2 data-i18n="charts.second_hop_v4">IPv4 Transit Analysis AS</h2>
      <div class="chart-wrap chart-wrap-wide chart-wrap-tall">
        <canvas id="pieSecondHopV4"></canvas>
      </div>
    </div>
    <div class="panel">
      <h2 data-i18n="charts.second_hop_v6">IPv6 Transit Analysis</h2>
      <div class="chart-wrap chart-wrap-wide chart-wrap-tall">
        <canvas id="pieSecondHopV6"></canvas>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h2 data-i18n="tables.top_communities">Top communities</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.community">Community</th>
              <th data-i18n="tables.count">Count</th>
              <th data-i18n="tables.percent_total">% total</th>
              <th data-i18n="tables.ipv4">IPv4</th>
              <th data-i18n="tables.ipv6">IPv6</th>
            </tr>
          </thead>
          <tbody>
            {% for row in top_communities %}
            <tr>
              <td class="mono">{{ row.community }}</td>
              <td>{{ row.count }}</td>
              <td>{{ row.pct }}</td>
              <td>{{ row.v4 }}</td>
              <td>{{ row.v6 }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h2 data-i18n="tables.top_origin_as">Top origin AS</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.origin_as">Origin AS</th>
              <th data-i18n="tables.count">Count</th>
            </tr>
          </thead>
          <tbody>
            {% for row in top_origin_as %}
            <tr>
              <td class="mono">{{ row.asn }}</td>
              <td>{{ row.count }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h2 data-i18n="tables.top_next_hops">Top next-hop</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.next_hop">Next-hop</th>
              <th data-i18n="tables.count">Count</th>
            </tr>
          </thead>
          <tbody>
            {% for row in top_next_hops %}
            <tr>
              <td class="mono">{{ row.next_hop }}</td>
              <td>{{ row.count }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h2 data-i18n="sections.operational_stats">Operational statistics</h2>
      <div class="section-space">
        <span class="tag"><span data-i18n="tags.routes_without_communities">Routes without communities</span>: {{ routes_without_communities }}</span>
        <span class="tag"><span data-i18n="tags.ipv4_with_prepend">IPv4 with prepend</span>: {{ routes_with_prepend_v4 }}</span>
        <span class="tag"><span data-i18n="tags.ipv6_with_prepend">IPv6 with prepend</span>: {{ routes_with_prepend_v6 }}</span>
      </div>
      <div class="section-space">
        <span class="tag"><span data-i18n="tags.self_community">Self community</span>: {{ community_self }}</span>
        <span class="tag"><span data-i18n="tags.customer_community">Customer community</span>: {{ community_customers }}</span>
      </div>
      <div class="section-space">
        <h2 data-i18n="tables.routes_without_communities">Routes without communities</h2>
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.afi">AFI</th>
              <th data-i18n="tables.prefix">Prefix</th>
              <th data-i18n="tables.next_hop">Next-Hop</th>
              <th data-i18n="tables.communities">Communities</th>
            </tr>
          </thead>
          <tbody>
          {% for row in routes_without_communities_rows %}
          <tr>
            <td>{{ row.afi_name }}</td>
            <td class="mono">{{ row.prefix }}</td>
            <td class="mono">{{ row.next_hop }}</td>
            <td class="mono">{{ row.communities }}</td>
          </tr>
          {% endfor %}
        </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h2 data-i18n="sections.blackhole_routes">Blackhole routes</h2>
      <div class="chart-wrap">
        <canvas id="pieBlackholePrefixLengths"></canvas>
      </div>
    </div>
    <div class="panel">
      <h2><span data-i18n="sections.blackhole_route_list">Blackhole route list</span> - <span data-i18n="tables.total_routes">Total routes</span>: {{ blackhole_total_routes }}</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.afi">AFI</th>
              <th data-i18n="tables.prefix">Prefix</th>
              <th data-i18n="tables.next_hop">Next-Hop</th>
              <th data-i18n="tables.communities">Communities</th>
            </tr>
          </thead>
          <tbody>
          {% for row in blackholed_rows %}
          <tr>
            <td>{{ row.afi_name }}</td>
            <td class="mono">{{ row.prefix }}</td>
            <td class="mono">{{ row.next_hop }}</td>
            <td class="mono">{{ row.communities }}</td>
          </tr>
          {% endfor %}
        </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h2 data-i18n="sections.mitigation_routes">Anti-DDoS mitigation routes</h2>
      <div class="chart-wrap">
        <canvas id="pieMitigationPrefixLengths"></canvas>
      </div>
    </div>
    <div class="panel">
      <h2><span data-i18n="sections.mitigation_route_list">Anti-DDoS route list</span> - <span data-i18n="tables.total_routes">Total routes</span>: {{ mitigation_total_routes }}</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.afi">AFI</th>
              <th data-i18n="tables.prefix">Prefix</th>
              <th data-i18n="tables.next_hop">Next-Hop</th>
              <th data-i18n="tables.communities">Communities</th>
            </tr>
          </thead>
          <tbody>
          {% for row in mitigation_rows %}
          <tr>
            <td>{{ row.afi_name }}</td>
            <td class="mono">{{ row.prefix }}</td>
            <td class="mono">{{ row.next_hop }}</td>
            <td class="mono">{{ row.communities }}</td>
          </tr>
          {% endfor %}
        </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="grid-1">
    <div class="panel">
      <h2><span data-i18n="sections.self_announcements">Self announcements</span> (<span data-i18n="tags.community">community</span> {{ community_self }})</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.afi">AFI</th>
              <th data-i18n="tables.prefix">Prefix</th>
              <th data-i18n="tables.next_hop">Next-Hop</th>
              <th data-i18n="tables.communities">Communities</th>
            </tr>
          </thead>
          <tbody>
            {% for row in self_rows %}
            <tr>
              <td>{{ row.afi_name }}</td>
              <td class="mono">{{ row.prefix }}</td>
              <td class="mono">{{ row.next_hop }}</td>
              <td class="mono">{{ row.communities }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h2><span data-i18n="sections.customer_announcements">Customer announcements</span> (<span data-i18n="tags.community">community</span> {{ community_customers }})</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="tables.afi">AFI</th>
              <th data-i18n="tables.prefix">Prefix</th>
              <th data-i18n="tables.as_path">AS-PATH</th>
              <th data-i18n="tables.origin_as">Origin AS</th>
              <th data-i18n="tables.next_hop">Next-Hop</th>
              <th data-i18n="tables.communities">Communities</th>
            </tr>
          </thead>
          <tbody>
            {% for row in customer_rows %}
            <tr>
              <td>{{ row.afi_name }}</td>
              <td class="mono">{{ row.prefix }}</td>
              <td class="mono">{{ row.as_path }}</td>
              <td class="mono">{{ row.origin_as }}</td>
              <td class="mono">{{ row.next_hop }}</td>
              <td class="mono">{{ row.communities }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <footer>
    <span data-i18n="footer.generated_for">Generated for</span> <span class="mono">{{ isp_name }}</span>.
  </footer>
</div>

<script>
const REPORT_I18N = {
  directory: {{ i18n_dir|tojson }},
  defaultLang: {{ default_lang|tojson }},
  supportedLangs: {{ supported_langs|tojson }},
  languageNames: {{ language_names|safe }},
  chartLabels: {
    ipv4: {{ chart_label_ipv4|tojson }},
    ipv6: {{ chart_label_ipv6|tojson }}
  }
};

function resolveLanguage() {
  const urlLang = new URLSearchParams(window.location.search).get('lang');
  const browserLang = (navigator.languages && navigator.languages[0]) || navigator.language || REPORT_I18N.defaultLang;
  const candidate = (urlLang || browserLang || REPORT_I18N.defaultLang).toLowerCase().split('-')[0];
  if (REPORT_I18N.supportedLangs.includes(candidate)) {
    return candidate;
  }
  return REPORT_I18N.defaultLang;
}

async function loadTranslations(lang) {
  const candidates = [lang, REPORT_I18N.defaultLang].filter((value, index, self) => value && self.indexOf(value) === index);

  for (const current of candidates) {
    try {
      const response = await fetch(`${REPORT_I18N.directory}/${current}.json`, { cache: 'no-cache' });
      if (response.ok) {
        return { lang: current, messages: await response.json() };
      }
    } catch (error) {
      console.warn('Could not load translations for', current, error);
    }
  }

  return { lang: REPORT_I18N.defaultLang, messages: {} };
}

function translate(messages, key, fallback) {
  return key.split('.').reduce((acc, segment) => (acc && acc[segment] !== undefined ? acc[segment] : null), messages) ?? fallback;
}

function applyTranslations(messages) {
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    const key = element.dataset.i18n;
    const fallback = element.dataset.i18nFallback || element.textContent;
    element.textContent = translate(messages, key, fallback);
  });
}

function initLanguageSelector(activeLang) {
  const select = document.getElementById('lang-select');
  if (!select) {
    return;
  }

  select.innerHTML = '';
  REPORT_I18N.supportedLangs.forEach((lang) => {
    const option = document.createElement('option');
    option.value = lang;
    option.textContent = REPORT_I18N.languageNames[lang] || lang;
    option.selected = lang === activeLang;
    select.appendChild(option);
  });

  select.addEventListener('change', () => {
    const url = new URL(window.location.href);
    url.searchParams.set('lang', select.value);
    window.location.href = url.toString();
  });
}

function makePie(id, labels, values) {
  new Chart(document.getElementById(id), {
    type: 'pie',
    data: {
      labels: labels,
      datasets: [{ data: values }]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e5e7eb' } } }
    }
  });
}

function makeBar(id, labels, datasets, stacked=false) {
  new Chart(document.getElementById(id), {
    type: 'bar',
    data: { labels: labels, datasets: datasets },
    options: {
      responsive: true,
      scales: {
        x: { stacked: stacked, ticks: { color: '#e5e7eb' }, grid: { color: '#374151' } },
        y: { stacked: stacked, ticks: { color: '#e5e7eb' }, grid: { color: '#374151' } }
      },
      plugins: { legend: { labels: { color: '#e5e7eb' } } }
    }
  });
}

function generateColorPalette(n) {
  const colors = [];
  for (let i = 0; i < n; i++) {
    const hue = (i * 360 / Math.max(n, 1)) % 360;
    colors.push(`hsl(${hue}, 70%, 60%)`);
  }
  return colors;
}

function shadeColor(hsl, deltaLightness) {
  const match = hsl.match(/hsl\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)%,\s*(\d+(?:\.\d+)?)%\)/);
  if (!match) {
    return hsl;
  }

  const h = match[1];
  const s = match[2];
  let l = parseFloat(match[3]);
  l = Math.max(28, Math.min(82, l + deltaLightness));
  return `hsl(${h}, ${s}%, ${l}%)`;
}

function makeNestedDoughnut(id, innerLabels, innerValues, outerLabels, outerValues, outerParents) {
  const baseColors = generateColorPalette(innerLabels.length);
  const parentToIndex = new Map(innerLabels.map((label, idx) => [label, idx]));
  const childOffsets = new Map();

  const innerColors = baseColors.slice();
  const outerColors = outerParents.map((parent) => {
    const parentIndex = parentToIndex.has(parent) ? parentToIndex.get(parent) : 0;
    const baseColor = baseColors[parentIndex] || 'hsl(210, 70%, 60%)';
    const currentOffset = childOffsets.get(parent) || 0;
    childOffsets.set(parent, currentOffset + 1);
    const lightnessShift = ((currentOffset % 8) - 3) * 5;
    return shadeColor(baseColor, lightnessShift);
  });

  const originalInnerValues = innerValues.slice();
  const originalOuterValues = outerValues.slice();
  const hiddenParents = new Set();

  const chart = new Chart(document.getElementById(id), {
    type: 'doughnut',
    data: {
      labels: [],
      datasets: [
     
        {
          label: 'Second hop',
          ring: 'outer',
          data: outerValues.slice(),
          labels: outerLabels,
          parents: outerParents,
          backgroundColor: outerColors,
          borderColor: '#e2e8f0',
          borderWidth: 1,
          spacing: 0,
          hoverOffset: 0,
          weight: 1
        },
        {
          label: 'First hop',
          ring: 'inner',
          data: innerValues.slice(),
          labels: innerLabels,
          backgroundColor: innerColors,
          borderColor: '#e2e8f0',
          borderWidth: 1,
          spacing: 0,
          hoverOffset: 0,
          weight: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '10%',
      animation: false,
      plugins: {
        legend: {
          display: true,
          labels: {
            color: '#e5e7eb',
            boxWidth: 26,
            boxHeight: 12,
            padding: 14,
            font: {
              size: 12
            },
            generateLabels: function(chart) {
              const dataset = chart.data.datasets[1];
              return dataset.labels.map((label, i) => ({
                text: label,
                fillStyle: dataset.backgroundColor[i],
                strokeStyle: dataset.backgroundColor[i],
                fontColor: '#e5e7eb',
                lineWidth: 1,
                hidden: hiddenParents.has(label),
                index: i,
                datasetIndex: 0
              }));
            }
          },
          onClick: function(e, legendItem, legend) {
            const chart = legend.chart;
            const index = legendItem.index;
          
            const metaInner = chart.getDatasetMeta(1); // first hop
            const metaOuter = chart.getDatasetMeta(0); // second hop
          
            const isVisible = !metaInner.data[index].hidden;
          
            // toggle first hop
            metaInner.data[index].hidden = isVisible;
          
            // toggle tutti i second hop associati
            metaOuter.data.forEach((arc, i) => {
              if (chart.data.datasets[0].parents[i] === chart.data.datasets[1].labels[index]) {
                arc.hidden = isVisible;
              }
            });
          
            chart.update();
          }
        },
        tooltip: {
          callbacks: {
            title: function() {
              return '';
            },
            label: function(context) {
              const ds = context.dataset;
              const idx = context.dataIndex;
              const value = context.raw;

              if (!value) {
                return '';
              }

              if (ds.ring === 'inner') {
                return `${ds.labels[idx]}: ${value} prefixes`;
              }

              return `${ds.parents[idx]} → ${ds.labels[idx]}: ${value} prefixes`;
            }
          },
          filter: function(context) {
            return !!context.raw;
          }
        }
      }
    }
  });

  return chart;
}

makePie('pieRoutes', {{ pie_routes_labels|safe }}, {{ pie_routes_values|safe }});
makeNestedDoughnut(
  'pieSecondHopV4',
  {{ second_hop_v4_inner_labels|safe }},
  {{ second_hop_v4_inner_values|safe }},
  {{ second_hop_v4_outer_labels|safe }},
  {{ second_hop_v4_outer_values|safe }},
  {{ second_hop_v4_outer_parents|safe }}
);
makeNestedDoughnut(
  'pieSecondHopV6',
  {{ second_hop_v6_inner_labels|safe }},
  {{ second_hop_v6_inner_values|safe }},
  {{ second_hop_v6_outer_labels|safe }},
  {{ second_hop_v6_outer_values|safe }},
  {{ second_hop_v6_outer_parents|safe }}
);
makePie('pieBlackholePrefixLengths', {{ blackhole_prefix_labels|safe }}, {{ blackhole_prefix_values|safe }});
makePie('pieMitigationPrefixLengths', {{ mitigation_prefix_labels|safe }}, {{ mitigation_prefix_values|safe }});

makeBar('histWithPrepend', {{ hist_with_labels|safe }}, [
  { label: REPORT_I18N.chartLabels.ipv4, data: {{ hist_with_v4|safe }} },
  { label: REPORT_I18N.chartLabels.ipv6, data: {{ hist_with_v6|safe }} }
]);

makeBar('histWithoutPrepend', {{ hist_without_labels|safe }}, [
  { label: REPORT_I18N.chartLabels.ipv4, data: {{ hist_without_v4|safe }} },
  { label: REPORT_I18N.chartLabels.ipv6, data: {{ hist_without_v6|safe }} }
]);

makeBar('barPrefixLen', {{ prefix_len_labels|safe }}, [
  { label: REPORT_I18N.chartLabels.ipv4, data: {{ prefix_len_v4|safe }} },
  { label: REPORT_I18N.chartLabels.ipv6, data: {{ prefix_len_v6|safe }} }
], false);

(function updateGeneratedAgo() {
  const generatedAtEl = document.getElementById('generated-at');
  const generatedAgoEl = document.getElementById('generated-ago');
  if (!generatedAtEl || !generatedAgoEl) {
    return;
  }

  const generatedAt = new Date(generatedAtEl.dataset.generatedAt);
  if (Number.isNaN(generatedAt.getTime())) {
    return;
  }

  function render() {
    const now = new Date();
    const diffMs = now - generatedAt;
    const diffMinutes = Math.max(0, Math.floor(diffMs / 60000));
    generatedAgoEl.textContent = `(${diffMinutes} min)`;
  }

  render();
  setInterval(render, 60000);
})();

(async function initI18n() {
  const preferredLang = resolveLanguage();
  const { lang, messages } = await loadTranslations(preferredLang);
  document.documentElement.lang = lang;
  applyTranslations(messages);
  initLanguageSelector(lang);
})();
</script>
</body>
</html>
"""


AS_TOKEN_RE = re.compile(r"\d+")
PREFIXLEN_V4_RE = re.compile(r"/(\d{1,2})$")
PREFIXLEN_V6_RE = re.compile(r"/(\d{1,3})$")


def fmt_float(value, ndigits=2):
    if value is None:
        return "0.00"
    return f"{value:.{ndigits}f}"


def fmt_int(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_number(value, ndigits=2):
    if value is None:
        value = 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"

    if number.is_integer():
        return fmt_int(int(number))

    return f"{number:,.{ndigits}f}"


def percentile(values, pct):
    if not values:
        return 0
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return vals[int(k)]
    d0 = vals[f] * (c - k)
    d1 = vals[c] * (k - f)
    return d0 + d1


def median(values):
    return percentile(values, 0.5)


def mean(values):
    return (sum(values) / len(values)) if values else 0.0


def parse_as_path(as_path):
    if not as_path:
        return []
    return [int(x) for x in AS_TOKEN_RE.findall(as_path)]


def dedup_consecutive(seq):
    if not seq:
        return []
    out = [seq[0]]
    for item in seq[1:]:
        if item != out[-1]:
            out.append(item)
    return out


def parse_communities(comm):
    if not comm:
        return []
    tokens = []
    for piece in re.split(r"[\s,]+", comm.strip()):
        piece = piece.strip()
        if not piece:
            continue
        if ":" in piece:
            tokens.append(piece)
    return tokens


def afi_name(afi):
    if afi == 1:
        return "IPv4"
    if afi == 2:
        return "IPv6"
    return str(afi)


def prefix_length(prefix, afi):
    if not prefix:
        return None
    if afi == 1:
        m = PREFIXLEN_V4_RE.search(prefix)
    elif afi == 2:
        m = PREFIXLEN_V6_RE.search(prefix)
    else:
        m = None
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def load_as2org_mapping(path):
    asn_to_org_id = {}
    org_id_to_name = {}

    if not os.path.exists(path):
        return {}

    section = None

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("# format:"):
                lower = line.lower()
                if "aut" in lower and "org_id" in lower:
                    section = "asns"
                elif "org_id" in lower and "org_name" in lower:
                    section = "orgs"
                else:
                    section = None
                continue

            if line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split("|")]

            if section == "asns":
                if len(parts) >= 4 and parts[0].isdigit():
                    asn = int(parts[0])
                    org_id = parts[3]
                    asn_to_org_id[asn] = org_id

            elif section == "orgs":
                if len(parts) >= 3:
                    org_id = parts[0]
                    org_name = parts[2]
                    org_id_to_name[org_id] = org_name

    mapping = {}
    for asn, org_id in asn_to_org_id.items():
        mapping[asn] = org_id_to_name.get(org_id, f"AS{asn}")

    return mapping


def asn_label(asn, asn_name_map):
    if asn is None or asn == "":
        return ""
    try:
        asn_int = int(asn)
    except (TypeError, ValueError):
        return str(asn)
    org = asn_name_map.get(asn_int)
    if org:
        return f"AS{asn_int} - {org}"
    return f"AS{asn_int}"


def build_nested_hop_chart(first_hop_counter, second_hop_tree, top_n_first=TOP_N_HOPS, top_n_second_per_first=None):
    first_items = first_hop_counter.most_common(top_n_first)

    inner_labels = []
    inner_values = []

    outer_labels = []
    outer_values = []
    outer_parents = []

    for first_label, first_count in first_items:
        inner_labels.append(first_label)
        inner_values.append(first_count)

        second_counter = second_hop_tree.get(first_label, Counter())
        second_items = second_counter.most_common(top_n_second_per_first)

        consumed = 0
        for second_label, second_count in second_items:
            outer_labels.append(second_label)
            outer_values.append(second_count)
            outer_parents.append(first_label)
            consumed += second_count

        remaining = first_count - consumed
        if remaining > 0:
            outer_labels.append("Other")
            outer_values.append(remaining)
            outer_parents.append(first_label)

    return {
        "inner_labels": json.dumps(inner_labels),
        "inner_values": json.dumps(inner_values),
        "outer_labels": json.dumps(outer_labels),
        "outer_values": json.dumps(outer_values),
        "outer_parents": json.dumps(outer_parents),
    }


def sql_fetch_rows():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    afi,
                    prefix::text,
                    COALESCE(as_path, ''),
                    COALESCE(origin_as::text, ''),
                    COALESCE(next_hop::text, ''),
                    COALESCE(communities, '')
                FROM current_rib
                WHERE peer_ip = %s::inet
                ORDER BY afi, prefix
                """,
                (PEER_IP,),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def build_report():
    asn_name_map = load_as2org_mapping(AS2ORG_FILE)

    total_routes = 0
    ipv4_count = 0
    ipv6_count = 0

    communities_total = Counter()
    communities_v4 = Counter()
    communities_v6 = Counter()

    first_hop_v4 = Counter()
    first_hop_v6 = Counter()
    second_hop_tree_v4 = defaultdict(Counter)
    second_hop_tree_v6 = defaultdict(Counter)

    path_with_v4 = []
    path_with_v6 = []
    path_without_v4 = []
    path_without_v6 = []

    origin_as_counter = Counter()
    next_hop_counter = Counter()

    prefixlen_v4 = Counter()
    prefixlen_v6 = Counter()
    blackhole_community_counter = Counter()
    mitigation_community_counter = Counter()

    self_rows = []
    customer_rows = []
    routes_without_communities_rows = []
    blackholed_rows = []
    mitigation_rows = []

    routes_without_communities = 0
    routes_with_prepend_v4 = 0
    routes_with_prepend_v6 = 0

    rows = sql_fetch_rows()

    for afi, prefix, as_path, origin_as, next_hop, communities in rows:
        total_routes += 1

        if afi == 1:
            ipv4_count += 1
        elif afi == 2:
            ipv6_count += 1

        if next_hop:
            next_hop_counter[next_hop] += 1

        if origin_as:
            origin_as_counter[origin_as] += 1

        comm_list = parse_communities(communities)
        if not comm_list:
            routes_without_communities += 1

        for comm in comm_list:
            communities_total[comm] += 1
            if afi == 1:
                communities_v4[comm] += 1
            elif afi == 2:
                communities_v6[comm] += 1

        path_nums = parse_as_path(as_path)
        path_unique = dedup_consecutive(path_nums)

        path_len_with = len(path_nums)
        path_len_without = len(path_unique)

        if afi == 1:
            path_with_v4.append(path_len_with)
            path_without_v4.append(path_len_without)
        elif afi == 2:
            path_with_v6.append(path_len_with)
            path_without_v6.append(path_len_without)

        if path_len_with > path_len_without:
            if afi == 1:
                routes_with_prepend_v4 += 1
            elif afi == 2:
                routes_with_prepend_v6 += 1

        if len(path_nums) >= 1:
            first_label = asn_label(path_nums[0], asn_name_map)
            if afi == 1:
                first_hop_v4[first_label] += 1
            elif afi == 2:
                first_hop_v6[first_label] += 1

        if len(path_nums) >= 2:
            first_label = asn_label(path_nums[0], asn_name_map)
            second_label = asn_label(path_nums[1], asn_name_map)
            if afi == 1:
                second_hop_tree_v4[first_label][second_label] += 1
            elif afi == 2:
                second_hop_tree_v6[first_label][second_label] += 1

        plen = prefix_length(prefix, afi)
        if plen is not None:
            if afi == 1:
                prefixlen_v4[str(plen)] += 1
            elif afi == 2:
                prefixlen_v6[str(plen)] += 1

        row = {
            "afi_name": afi_name(afi),
            "prefix": prefix,
            "as_path": as_path,
            "origin_as": asn_label(origin_as, asn_name_map) if origin_as else "",
            "next_hop": next_hop,
            "communities": communities,
        }

        if COMMUNITY_SELF in comm_list:
            self_rows.append(row)
        if COMMUNITY_CUSTOMERS in comm_list:
            customer_rows.append(row)

        bh_matches = [c for c in comm_list if BH_RE.match(c)]
        if bh_matches:
            blackholed_rows.append(row)
            for community in bh_matches:
                blackhole_community_counter[community] += 1

        mitigation_matches = [c for c in comm_list if MITIGATION_RE.match(c)]
        if mitigation_matches:
            mitigation_rows.append(row)
            for community in mitigation_matches:
                mitigation_community_counter[community] += 1

        if not comm_list:
            routes_without_communities_rows.append(row)

    routes_with_prepend = routes_with_prepend_v4 + routes_with_prepend_v6

    top_communities = []
    for comm, count in communities_total.most_common(TOP_N_COMMUNITIES):
        pct = (count / total_routes * 100.0) if total_routes else 0.0
        top_communities.append(
            {
                "community": comm,
                "count": fmt_int(count),
                "pct": fmt_float(pct),
                "v4": fmt_int(communities_v4.get(comm, 0)),
                "v6": fmt_int(communities_v6.get(comm, 0)),
            }
        )

    top_origin_as = [
        {"asn": asn_label(asn, asn_name_map), "count": fmt_int(count)}
        for asn, count in origin_as_counter.most_common(TOP_N_ORIGIN_AS)
    ]

    top_next_hops = [
        {"next_hop": nh, "count": fmt_int(count)}
        for nh, count in next_hop_counter.most_common(TOP_N_NEXT_HOPS)
    ]

    hist_with_max = max(path_with_v4 + path_with_v6 + [0])
    hist_without_max = max(path_without_v4 + path_without_v6 + [0])

    hist_with_labels = [str(i) for i in range(0, hist_with_max + 1)]
    hist_without_labels = [str(i) for i in range(0, hist_without_max + 1)]

    hist_with_v4_counter = Counter(path_with_v4)
    hist_with_v6_counter = Counter(path_with_v6)
    hist_without_v4_counter = Counter(path_without_v4)
    hist_without_v6_counter = Counter(path_without_v6)

    hist_with_v4 = [hist_with_v4_counter.get(i, 0) for i in range(0, hist_with_max + 1)]
    hist_with_v6 = [hist_with_v6_counter.get(i, 0) for i in range(0, hist_with_max + 1)]
    hist_without_v4 = [hist_without_v4_counter.get(i, 0) for i in range(0, hist_without_max + 1)]
    hist_without_v6 = [hist_without_v6_counter.get(i, 0) for i in range(0, hist_without_max + 1)]

    prefix_len_keys = sorted({int(k) for k in list(prefixlen_v4.keys()) + list(prefixlen_v6.keys())})
    prefix_len_labels = [str(k) for k in prefix_len_keys]
    prefix_len_v4 = [prefixlen_v4.get(str(k), 0) for k in prefix_len_keys]
    prefix_len_v6 = [prefixlen_v6.get(str(k), 0) for k in prefix_len_keys]

    nested_second_hop_v4 = build_nested_hop_chart(
        first_hop_v4,
        second_hop_tree_v4,
        top_n_first=TOP_N_HOPS,
    )
    nested_second_hop_v6 = build_nested_hop_chart(
        first_hop_v6,
        second_hop_tree_v6,
        top_n_first=TOP_N_HOPS,
    )

    context = {
        "title": REPORT_TITLE,
        "isp_name": ISP_NAME,
        "peer_ip": PEER_IP,
        "i18n_dir": I18N_DIR,
        "default_lang": DEFAULT_LANG,
        "supported_langs": SUPPORTED_LANGS,
        "language_names": json.dumps({"en": "English", "it": "Italiano"}),
        "chart_label_ipv4": "IPv4",
        "chart_label_ipv6": "IPv6",
        "generated_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generated_at_iso": datetime.now(timezone.utc).astimezone().isoformat(),
        "total_routes": fmt_int(total_routes),
        "ipv4_count": fmt_int(ipv4_count),
        "ipv6_count": fmt_int(ipv6_count),
        "avg_path_with_prepend": fmt_number(mean(path_with_v4 + path_with_v6)),
        "avg_path_without_prepend": fmt_number(mean(path_without_v4 + path_without_v6)),
        "avg_v4_with_prepend": fmt_number(mean(path_with_v4)),
        "avg_v6_with_prepend": fmt_number(mean(path_with_v6)),
        "avg_v4_without_prepend": fmt_number(mean(path_without_v4)),
        "avg_v6_without_prepend": fmt_number(mean(path_without_v6)),
        "med_v4_with_prepend": fmt_number(median(path_with_v4)),
        "med_v6_with_prepend": fmt_number(median(path_with_v6)),
        "med_v4_without_prepend": fmt_number(median(path_without_v4)),
        "med_v6_without_prepend": fmt_number(median(path_without_v6)),
        "p95_v4_with_prepend": fmt_number(percentile(path_with_v4, 0.95)),
        "p95_v6_with_prepend": fmt_number(percentile(path_with_v6, 0.95)),
        "p95_v4_without_prepend": fmt_number(percentile(path_without_v4, 0.95)),
        "p95_v6_without_prepend": fmt_number(percentile(path_without_v6, 0.95)),
        "routes_with_prepend": fmt_int(routes_with_prepend),
        "routes_with_prepend_v4": fmt_int(routes_with_prepend_v4),
        "routes_with_prepend_v6": fmt_int(routes_with_prepend_v6),
        "routes_without_communities": fmt_int(routes_without_communities),
        "routes_without_communities_rows": routes_without_communities_rows,
        "blackholed_rows": blackholed_rows,
        "blackhole_total_routes": fmt_int(len(blackholed_rows)),
        "blackhole_prefix_labels": json.dumps([k for k, _ in sorted(blackhole_community_counter.items(), key=lambda item: item[0])]),
        "blackhole_prefix_values": json.dumps([v for _, v in sorted(blackhole_community_counter.items(), key=lambda item: item[0])]),
        "mitigation_rows": mitigation_rows,
        "mitigation_total_routes": fmt_int(len(mitigation_rows)),
        "mitigation_prefix_labels": json.dumps([k for k, _ in sorted(mitigation_community_counter.items(), key=lambda item: item[0])]),
        "mitigation_prefix_values": json.dumps([v for _, v in sorted(mitigation_community_counter.items(), key=lambda item: item[0])]),
        "self_count": fmt_int(len(self_rows) + len(customer_rows)),
        "community_self": COMMUNITY_SELF,
        "community_customers": COMMUNITY_CUSTOMERS,
        "top_communities": top_communities,
        "top_origin_as": top_origin_as,
        "top_next_hops": top_next_hops,
        "self_rows": self_rows,
        "customer_rows": customer_rows,
        "pie_routes_labels": json.dumps(["IPv4", "IPv6"]),
        "pie_routes_values": json.dumps([ipv4_count, ipv6_count]),
        "second_hop_v4_inner_labels": nested_second_hop_v4["inner_labels"],
        "second_hop_v4_inner_values": nested_second_hop_v4["inner_values"],
        "second_hop_v4_outer_labels": nested_second_hop_v4["outer_labels"],
        "second_hop_v4_outer_values": nested_second_hop_v4["outer_values"],
        "second_hop_v4_outer_parents": nested_second_hop_v4["outer_parents"],
        "second_hop_v6_inner_labels": nested_second_hop_v6["inner_labels"],
        "second_hop_v6_inner_values": nested_second_hop_v6["inner_values"],
        "second_hop_v6_outer_labels": nested_second_hop_v6["outer_labels"],
        "second_hop_v6_outer_values": nested_second_hop_v6["outer_values"],
        "second_hop_v6_outer_parents": nested_second_hop_v6["outer_parents"],
        "hist_with_labels": json.dumps(hist_with_labels),
        "hist_with_v4": json.dumps(hist_with_v4),
        "hist_with_v6": json.dumps(hist_with_v6),
        "hist_without_labels": json.dumps(hist_without_labels),
        "hist_without_v4": json.dumps(hist_without_v4),
        "hist_without_v6": json.dumps(hist_without_v6),
        "prefix_len_labels": json.dumps(prefix_len_labels),
        "prefix_len_v4": json.dumps(prefix_len_v4),
        "prefix_len_v6": json.dumps(prefix_len_v6),
    }

    return Template(HTML_TEMPLATE).render(**context)


def write_atomic(path, content):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".frt-report-", suffix=".html", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main():
    html = build_report()
    write_atomic(OUTPUT_HTML, html)
    print(f"Report written to {OUTPUT_HTML}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error while generating the report: {exc}", file=sys.stderr)
        sys.exit(1)

