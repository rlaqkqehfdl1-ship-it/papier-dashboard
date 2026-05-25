import requests, json, base64, os
from datetime import datetime, timedelta
from collections import defaultdict

GH_PAT      = os.environ.get("GH_PAT", "")
GH_REPO     = os.environ.get("GH_REPO", "rlaqkqehfdl1-ship-it/papier-dashboard")

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
orders_all    = get_all_orders(all_start, today, embed="items")
orders_month  = [o for o in orders_all if o["order_date"][:7] == datetime.now().strftime("%Y-%m")]
orders_today  = [o for o in orders_all if o["order_date"][:10] == today]
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

# 상품별 판매 수량 (오픈일 이후 누적)
sold_by_name = defaultdict(int)
for o in orders_all:
    for item in o.get("items", []):
        sold_by_name[item["product_name"]] += int(item.get("quantity", 0))

low_stock = []  # JS가 stock.json 기반으로 동적 계산

# ── HTML 생성 ─────────────────────────────────
now_str   = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 기준") + " · 매일 오전 10시 자동 갱신"
sold_json = json.dumps(dict(sold_by_name), ensure_ascii=False)
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
          <th style="text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500">기초재고</th>
          <th style="text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500">판매수량</th>
          <th style="text-align:left;padding:10px;border-bottom:2px solid #eee;color:#888;font-weight:500">잔여재고</th>
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
const GH_REPO_  = 'papier-dashboard';
const SOLD      = {sold_json};   // 판매수량 (빌드 시점 기준)
let stockSha = null, stockData = null;

function getGHToken() {{
  let tok = localStorage.getItem('gh_token');
  if (!tok) {{
    tok = prompt('GitHub Personal Access Token을 입력하세요:\\n(처음 한 번만 입력하면 저장됩니다)');
    if (tok) localStorage.setItem('gh_token', tok.trim());
  }}
  return tok ? tok.trim() : null;
}}

async function loadStock() {{
  try {{
    const r = await fetch(`https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO_}}/contents/stock.json`);
    const meta = await r.json();
    stockSha = meta.sha;
    const binary = atob(meta.content.replace(/\\n/g, ''));
    const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
    stockData = JSON.parse(new TextDecoder('utf-8').decode(bytes));
    renderStock();
  }} catch(e) {{
    document.getElementById('stock-tbody').innerHTML =
      '<tr><td colspan="5" style="padding:20px;color:#aaa;text-align:center">재고 데이터를 불러올 수 없습니다</td></tr>';
  }}
}}

function remColor(rem) {{
  return rem <= 0 ? '#e53' : rem <= 5 ? '#e96' : '#2a7';
}}

function renderStock() {{
  const tbody = document.getElementById('stock-tbody');
  let html = '', prev = null, lowCount = 0;
  stockData.products.forEach((p, pi) => {{
    const sold = SOLD[p.product_name] || 0;
    p.variants.forEach((v, vi) => {{
      const base = v.base_qty ?? v.qty ?? 0;
      const rem  = base - sold;
      if (rem <= 5) lowCount++;
      const showName = prev !== p.product_name;
      prev = p.product_name;
      html += `<tr>
        ${{showName
          ? `<td style="padding:10px;border-bottom:1px solid #f5f5f5;font-weight:600">${{p.product_name}}</td>`
          : '<td style="padding:10px;border-bottom:1px solid #f5f5f5"></td>'}}
        <td style="padding:10px;border-bottom:1px solid #f5f5f5;color:#666;font-size:12px">${{v.option}}</td>
        <td style="padding:10px;border-bottom:1px solid #f5f5f5">
          <input class="qty-input" type="number" min="0" value="${{base}}"
            data-pi="${{pi}}" data-vi="${{vi}}" data-sold="${{sold}}" onchange="onBaseChange(this)">
        </td>
        <td style="padding:10px;border-bottom:1px solid #f5f5f5;color:#888">${{sold}}개</td>
        <td id="rem-${{pi}}-${{vi}}" style="padding:10px;border-bottom:1px solid #f5f5f5;font-weight:700;color:${{remColor(rem)}}">${{rem}}개</td>
      </tr>`;
    }});
  }});
  tbody.innerHTML = html;
  const kpi = document.getElementById('low-stock-kpi');
  if (kpi) {{ kpi.textContent = lowCount + '개'; kpi.style.color = lowCount > 0 ? '#e53' : '#2a7'; }}
  document.getElementById('stock-status').textContent =
    `마지막 저장: ${{stockData.updated_at || '미설정'}} · 판매수량은 매일 오전 10시 갱신`;
}}

function onBaseChange(input) {{
  const base = parseInt(input.value) || 0;
  const sold = parseInt(input.dataset.sold) || 0;
  const rem  = base - sold;
  const pi = input.dataset.pi, vi = input.dataset.vi;
  const el = document.getElementById(`rem-${{pi}}-${{vi}}`);
  el.textContent = rem + '개';
  el.style.color = remColor(rem);
}}

async function saveStock() {{
  const token = getGHToken();
  if (!token) {{ alert('토큰이 없으면 저장할 수 없습니다.'); return; }}
  document.querySelectorAll('.qty-input').forEach(inp => {{
    const p = stockData.products[inp.dataset.pi];
    const v = p.variants[inp.dataset.vi];
    v.base_qty = parseInt(inp.value) || 0;
    delete v.qty;
  }});
  stockData.updated_at = new Date().toISOString().slice(0, 10);
  const text = JSON.stringify(stockData, null, 2);
  const encBytes = new TextEncoder().encode(text);
  let bin = ''; encBytes.forEach(b => bin += String.fromCharCode(b));
  const content = btoa(bin);
  const btn = document.getElementById('save-btn');
  btn.disabled = true; btn.textContent = '저장 중...';
  const r = await fetch(`https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO_}}/contents/stock.json`, {{
    method: 'PUT',
    headers: {{ 'Authorization': `Bearer ${{token}}`, 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json' }},
    body: JSON.stringify({{ message: `재고 기초 업데이트 ${{stockData.updated_at}}`, content, sha: stockSha }})
  }});
  btn.disabled = false; btn.textContent = '저장';
  if (r.ok) {{
    const res = await r.json();
    stockSha = res.content.sha;
    document.getElementById('stock-status').textContent =
      `마지막 저장: ${{stockData.updated_at}} · 판매수량은 매일 오전 10시 갱신`;
    alert('저장 완료!');
  }} else {{
    const err = await r.json();
    alert(`저장 실패: ${{err.message}}`);
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
