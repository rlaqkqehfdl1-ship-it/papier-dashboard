import requests, json, base64
from datetime import datetime, timedelta
from collections import defaultdict

CLIENT_ID     = "J2dzflmWekLd28v00yHuUK"
CLIENT_SECRET = "eb6beJ7TAkbTemPZfEA5mi"
MALL_ID       = "papierarchive"
TOKEN_FILE    = "tokens.json"
BASE          = f"https://{MALL_ID}.cafe24api.com/api/v2/admin"
API_VER       = "2026-03-01"

SHIP_STATUS = {
    "F": "배송준비중", "M": "배송중", "T": "배송완료",
    "C": "취소", "R": "반품", "E": "교환",
    "A": "결제전", "B": "입금전", "D": "배송보류"
}

def get_token():
    tokens = json.load(open(TOKEN_FILE))
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    if datetime.now() >= expires_at - timedelta(minutes=10):
        cred = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        r = requests.post(f"https://{MALL_ID}.cafe24api.com/api/v2/oauth/token",
            headers={"Authorization": f"Basic {cred}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
        tokens = r.json()
        json.dump(tokens, open(TOKEN_FILE, "w"), indent=2)
    return tokens["access_token"]

def H():
    return {"Authorization": f"Bearer {get_token()}", "X-Cafe24-Api-Version": API_VER}

def get(path, **params):
    return requests.get(f"{BASE}{path}", headers=H(), params=params).json()

def get_all_orders(start_date, end_date, embed=None):
    """90일 단위로 나눠서 전체 주문 수집 (Cafe24 API 날짜 범위 제한 대응)"""
    from datetime import datetime, timedelta
    all_orders = []
    cur = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while cur <= end:
        chunk_end = min(cur + timedelta(days=89), end)
        params = {
            "start_date": cur.strftime("%Y-%m-%d"),
            "end_date": chunk_end.strftime("%Y-%m-%d"),
            "limit": 100,
        }
        if embed:
            params["embed"] = embed
        offset = 0
        while True:
            params["offset"] = offset
            batch = requests.get(f"{BASE}/orders", headers=H(), params=params).json().get("orders", [])
            all_orders.extend(batch)
            if len(batch) < 100:
                break
            offset += 100
        cur = chunk_end + timedelta(days=1)
    return all_orders

# ── 데이터 수집 ──────────────────────────────
today       = datetime.now().strftime("%Y-%m-%d")
month_start = datetime.now().strftime("%Y-%m-01")
all_start   = "2026-04-17"  # 쇼핑몰 오픈일

print("데이터 수집 중...")
orders_month  = get_all_orders(month_start, today, embed="items")
orders_today  = [o for o in orders_month if o["order_date"][:10] == today]
orders_all    = get_all_orders(all_start, today)
products      = get("/products", limit=100).get("products", [])

# ── 집계 ─────────────────────────────────────
total_month  = sum(float(o["actual_order_amount"]["order_price_amount"]) for o in orders_month)
total_today  = sum(float(o["actual_order_amount"]["order_price_amount"]) for o in orders_today)
total_all    = sum(float(o["actual_order_amount"]["order_price_amount"]) for o in orders_all)
order_count  = len(orders_month)
order_count_all = len(orders_all)

status_count = defaultdict(int)
for o in orders_month:
    status_count[SHIP_STATUS.get(o.get("shipping_status",""), o.get("shipping_status","기타"))] += 1

product_sales = defaultdict(int)
for o in orders_month:
    for item in o.get("items", []):
        product_sales[item["product_name"]] += int(item.get("quantity", 0))

bestsellers = sorted(product_sales.items(), key=lambda x: -x[1])[:10]

daily_sales = defaultdict(float)
for o in orders_month:
    day = o["order_date"][:10]
    daily_sales[day] += float(o["actual_order_amount"]["order_price_amount"])
daily_sorted = sorted(daily_sales.items())

low_stock     = []  # stock.json에서 JS가 동적으로 처리

# ── HTML 생성 ─────────────────────────────────
now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 기준") + " · 매일 오전 10시 자동 갱신"
chart_labels = json.dumps([d[0][5:] for d in daily_sorted])
chart_data   = json.dumps([d[1] for d in daily_sorted])

status_labels = json.dumps(list(status_count.keys()))
status_vals   = json.dumps(list(status_count.values()))

best_labels = json.dumps([b[0] for b in bestsellers])
best_vals   = json.dumps([b[1] for b in bestsellers])


status_rows = "".join(f'<div class="stat-chip"><span>{k}</span><strong>{v}건</strong></div>' for k,v in status_count.items())
best_rows   = "".join(f'<li><span class="rank">{i+1}</span><span class="pname">{b[0]}</span><span class="qty">{b[1]}개</span></li>' for i,b in enumerate(bestsellers))

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>papier archive 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Apple SD Gothic Neo',sans-serif;background:#f5f5f5;color:#222}}
  header{{background:#111;color:#fff;padding:20px 32px;display:flex;justify-content:space-between;align-items:center}}
  header h1{{font-size:20px;font-weight:300;letter-spacing:4px}}
  header span{{font-size:12px;opacity:.6}}
  .container{{max-width:1200px;margin:0 auto;padding:24px}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}}
  .kpi{{background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  .kpi .label{{font-size:12px;color:#888;margin-bottom:8px}}
  .kpi .value{{font-size:28px;font-weight:700;color:#111}}
  .kpi .sub{{font-size:12px;color:#aaa;margin-top:4px}}
  .grid2{{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:24px}}
  .grid2b{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
  .card{{background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  .card h2{{font-size:14px;font-weight:600;color:#444;margin-bottom:20px;letter-spacing:1px}}
  .stat-chips{{display:flex;flex-wrap:wrap;gap:10px}}
  .stat-chip{{background:#f8f8f8;border-radius:8px;padding:10px 16px;display:flex;flex-direction:column;gap:4px}}
  .stat-chip span{{font-size:11px;color:#888}}
  .stat-chip strong{{font-size:18px;font-weight:700}}
  ol.best-list{{list-style:none;padding:0}}
  ol.best-list li{{display:flex;align-items:center;padding:10px 0;border-bottom:1px solid #f0f0f0;gap:12px}}
  .rank{{font-size:12px;font-weight:700;color:#bbb;width:20px;text-align:center}}
  li:nth-child(1) .rank{{color:#f0c040}}
  li:nth-child(2) .rank{{color:#aaa}}
  li:nth-child(3) .rank{{color:#c87533}}
  .pname{{flex:1;font-size:13px}}
  .qty{{font-size:13px;font-weight:600;color:#555}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500}}
  td{{padding:10px;border-bottom:1px solid #f5f5f5}}
  .badge{{font-size:11px;padding:3px 8px;border-radius:20px;font-weight:600}}
  .badge-danger{{background:#fff0f0;color:#e53}}
  .badge-ok{{background:#f0fff4;color:#2a7}}
  .badge-out{{background:#f0f0f0;color:#999}}
  .product-name-cell{{font-weight:600;padding-top:14px}}
  .opt-cell{{color:#666;font-size:12px}}
  .qty-input{{width:64px;border:1px solid #ddd;border-radius:6px;padding:3px 8px;font-size:13px;text-align:right}}
  .qty-input:focus{{outline:none;border-color:#111}}
  .save-btn{{background:#111;color:#fff;border:none;border-radius:8px;padding:10px 24px;font-size:13px;cursor:pointer;margin-top:16px}}
  .save-btn:hover{{background:#333}}
  .save-btn:disabled{{background:#aaa;cursor:default}}
  .stock-status{{font-size:12px;color:#aaa;margin-top:8px}}
  canvas{{max-height:220px}}
</style>
</head>
<body>
<header>
  <h1>papier archive</h1>
  <span>{now_str}</span>
</header>
<div class="container">

  <div class="kpi-grid">
    <div class="kpi"><div class="label">누적 총 매출</div><div class="value">{int(total_all):,}원</div><div class="sub">전체 기간 · {order_count_all}건</div></div>
    <div class="kpi"><div class="label">이번달 총 매출</div><div class="value">{int(total_month):,}원</div><div class="sub">{month_start} ~ {today} · {order_count}건</div></div>
    <div class="kpi"><div class="label">오늘 매출</div><div class="value">{int(total_today):,}원</div><div class="sub">{today}</div></div>
    <div class="kpi"><div class="label">재고 부족 상품</div><div class="value" id="low-stock-kpi" style="color:#aaa">-</div><div class="sub">5개 이하 기준</div></div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>일별 매출 추이</h2>
      <canvas id="salesChart"></canvas>
    </div>
    <div class="card">
      <h2>주문 처리 현황</h2>
      <div class="stat-chips">{status_rows}</div>
      <br>
      <canvas id="statusChart"></canvas>
    </div>
  </div>

  <div class="grid2b">
    <div class="card">
      <h2>베스트셀러</h2>
      <ol class="best-list">{best_rows}</ol>
    </div>
    <div class="card">
      <h2>재고 관리</h2>
      <table id="stock-table" style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr>
          <th style="text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500">상품명</th>
          <th style="text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500">옵션</th>
          <th style="text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500">재고</th>
          <th style="text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500">상태</th>
        </tr></thead>
        <tbody id="stock-tbody"><tr><td colspan="4" style="padding:20px;color:#aaa;text-align:center">불러오는 중...</td></tr></tbody>
      </table>
      <button class="save-btn" id="save-btn" onclick="saveStock()">저장</button>
      <div class="stock-status" id="stock-status"></div>
    </div>
  </div>

</div>
<script>
new Chart(document.getElementById('salesChart'), {{
  type: 'bar',
  data: {{ labels: {chart_labels}, datasets: [{{ label: '매출(원)', data: {chart_data},
    backgroundColor: 'rgba(17,17,17,0.12)', borderColor: '#111', borderWidth: 1.5, borderRadius: 4 }}] }},
  options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ ticks: {{ callback: v => v.toLocaleString()+'원' }} }} }} }}
}});
// ── 재고 관리 ─────────────────────────────────
const GH_OWNER = 'rlaqkqehfdl1-ship-it';
const GH_REPO  = 'papier-dashboard';
let stockSha = null, stockData = null;
let ghToken = sessionStorage.getItem('gh_token') || '';

async function loadStock() {{
  try {{
    const r = await fetch(`https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/contents/stock.json`);
    const meta = await r.json();
    stockSha = meta.sha;
    stockData = JSON.parse(atob(meta.content.replace(/\\n/g, '')));
    renderStock();
    updateLowStockKpi();
  }} catch(e) {{
    document.getElementById('stock-tbody').innerHTML =
      '<tr><td colspan="4" style="padding:20px;color:#aaa;text-align:center">재고 데이터를 불러올 수 없습니다</td></tr>';
  }}
}}

function renderStock() {{
  const tbody = document.getElementById('stock-tbody');
  let html = '', prev = null;
  stockData.products.forEach((p, pi) => {{
    p.variants.forEach((v, vi) => {{
      const showName = prev !== p.product_name;
      prev = p.product_name;
      html += `<tr>
        ${{showName ? `<td class="product-name-cell" style="padding:10px;border-bottom:1px solid #f5f5f5;font-weight:600">${{p.product_name}}</td>` : '<td style="padding:10px;border-bottom:1px solid #f5f5f5"></td>'}}
        <td class="opt-cell" style="padding:10px;border-bottom:1px solid #f5f5f5;color:#666;font-size:12px">${{v.option}}</td>
        <td style="padding:10px;border-bottom:1px solid #f5f5f5">
          <input class="qty-input" type="number" min="0" value="${{v.qty}}" data-pi="${{pi}}" data-vi="${{vi}}" onchange="onQtyChange(this)">
        </td>
        <td style="padding:10px;border-bottom:1px solid #f5f5f5" id="badge-${{pi}}-${{vi}}">${{qtyBadge(v.qty)}}</td>
      </tr>`;
    }});
  }});
  tbody.innerHTML = html;
  document.getElementById('stock-status').textContent =
    `마지막 저장: ${{stockData.updated_at || '없음'}}`;
}}

function qtyBadge(qty) {{
  if (qty === 0) return '<span class="badge badge-out">품절</span>';
  if (qty <= 5)  return '<span class="badge badge-danger">부족</span>';
  return '<span class="badge badge-ok">정상</span>';
}}

function onQtyChange(input) {{
  const qty = parseInt(input.value) || 0;
  const pi = input.dataset.pi, vi = input.dataset.vi;
  document.getElementById(`badge-${{pi}}-${{vi}}`).innerHTML = qtyBadge(qty);
}}

function updateLowStockKpi() {{
  if (!stockData) return;
  const low = stockData.products.flatMap(p => p.variants).filter(v => v.qty <= 5).length;
  const el = document.getElementById('low-stock-kpi');
  if (el) {{ el.textContent = low + '개'; el.style.color = low > 0 ? '#e53' : '#2a7'; }}
}}

async function saveStock() {{
  if (!ghToken) {{
    ghToken = prompt('GitHub Personal Access Token을 입력하세요:\\n(repo 권한 필요 — 한 번만 입력하면 세션 동안 저장됩니다)');
    if (!ghToken) return;
    sessionStorage.setItem('gh_token', ghToken);
  }}
  document.querySelectorAll('.qty-input').forEach(inp => {{
    stockData.products[inp.dataset.pi].variants[inp.dataset.vi].qty = parseInt(inp.value) || 0;
  }});
  stockData.updated_at = new Date().toISOString().slice(0, 10);
  const content = btoa(unescape(encodeURIComponent(JSON.stringify(stockData, null, 2))));
  const btn = document.getElementById('save-btn');
  btn.disabled = true; btn.textContent = '저장 중...';
  const r = await fetch(`https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/contents/stock.json`, {{
    method: 'PUT',
    headers: {{ 'Authorization': `Bearer ${{ghToken}}`, 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json' }},
    body: JSON.stringify({{ message: `재고 업데이트 ${{stockData.updated_at}}`, content, sha: stockSha }})
  }});
  btn.disabled = false; btn.textContent = '저장';
  if (r.ok) {{
    const res = await r.json();
    stockSha = res.content.sha;
    document.getElementById('stock-status').textContent = `마지막 저장: ${{stockData.updated_at}}`;
    updateLowStockKpi();
    alert('저장 완료!');
  }} else {{
    const err = await r.json();
    alert(`저장 실패: ${{err.message}}`);
    if (r.status === 401) {{ ghToken = ''; sessionStorage.removeItem('gh_token'); }}
  }}
}}

loadStock();

// ── 차트 ──────────────────────────────────────
new Chart(document.getElementById('statusChart'), {{
  type: 'doughnut',
  data: {{ labels: {status_labels}, datasets: [{{ data: {status_vals},
    backgroundColor: ['#111','#555','#888','#bbb','#ddd','#eee'] }}] }},
  options: {{ plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }} }} }}
}});
</script>
</body>
</html>"""

with open("dashboard.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"dashboard.html 생성 완료!")
print(f"   이번달 매출: {int(total_month):,}원 / 주문 {order_count}건")
print(f"   브라우저에서 dashboard.html 파일을 열어보세요")

import os
if not os.environ.get("CI"):
    import webbrowser
    webbrowser.open("file://" + os.path.abspath("dashboard.html"))
