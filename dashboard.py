import requests, json, base64, os, hashlib
from datetime import datetime, timedelta
from collections import defaultdict

GH_PAT      = os.environ.get("GH_PAT", "")
GH_REPO     = os.environ.get("GH_REPO", "rlaqkqehfdl1-ship-it/papier-dashboard")
DASH_USER   = os.environ.get("DASH_USER", "papierarchive")
DASH_PASS   = os.environ.get("DASH_PASS", "3571425qaz!")
user_hash   = hashlib.sha256(DASH_USER.encode()).hexdigest()
pass_hash   = hashlib.sha256(DASH_PASS.encode()).hexdigest()
if GH_PAT:
    _b64 = base64.b64encode(GH_PAT.encode()).decode()
    _mid = len(_b64) // 2
    pat_a, pat_b = _b64[:_mid], _b64[_mid:]
else:
    pat_a = pat_b = ""

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
    all_orders = []
    cur = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while cur <= end:
        chunk_end = min(cur + timedelta(days=89), end)
        params = {"start_date": cur.strftime("%Y-%m-%d"), "end_date": chunk_end.strftime("%Y-%m-%d"), "limit": 100}
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
all_start   = "2026-04-17"

print("데이터 수집 중...")
orders_all   = get_all_orders(all_start, today, embed="items")
orders_month = [o for o in orders_all if o["order_date"][:7] == datetime.now().strftime("%Y-%m")]
orders_today = [o for o in orders_all if o["order_date"][:10] == today]
products     = get("/products", limit=100).get("products", [])

real_products       = [p for p in products if float(p.get("price", "0")) > 0]
product_names_json  = json.dumps([p["product_name"] for p in real_products], ensure_ascii=False)
product_prices_json = json.dumps({p["product_name"]: int(float(p.get("price", "0"))) for p in real_products}, ensure_ascii=False)

# ── 집계 ─────────────────────────────────────
total_month     = sum(float(o["actual_order_amount"]["order_price_amount"]) for o in orders_month)
total_today     = sum(float(o["actual_order_amount"]["order_price_amount"]) for o in orders_today)
total_all       = sum(float(o["actual_order_amount"]["order_price_amount"]) for o in orders_all)
order_count     = len(orders_month)
order_count_all = len(orders_all)

status_count = defaultdict(int)
for o in orders_month:
    status_count[SHIP_STATUS.get(o.get("shipping_status", ""), o.get("shipping_status", "기타"))] += 1

product_sales = defaultdict(int)
for o in orders_month:
    for item in o.get("items", []):
        product_sales[item["product_name"]] += int(item.get("quantity", 0))

bestsellers  = sorted(product_sales.items(), key=lambda x: -x[1])[:10]
daily_sales  = defaultdict(float)
for o in orders_month:
    daily_sales[o["order_date"][:10]] += float(o["actual_order_amount"]["order_price_amount"])
daily_sorted = sorted(daily_sales.items())

sold_by_name = defaultdict(int)
for o in orders_all:
    for item in o.get("items", []):
        sold_by_name[item["product_name"]] += int(item.get("quantity", 0))

# ── HTML 변수 준비 ────────────────────────────
now_str       = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 기준") + " · 매일 오전 10시 자동 갱신"
sold_json     = json.dumps(dict(sold_by_name), ensure_ascii=False)
chart_labels  = json.dumps([d[0][5:] for d in daily_sorted])
chart_data    = json.dumps([d[1] for d in daily_sorted])
status_labels = json.dumps(list(status_count.keys()))
status_vals   = json.dumps(list(status_count.values()))
best_labels   = json.dumps([b[0] for b in bestsellers])
best_vals     = json.dumps([b[1] for b in bestsellers])
status_rows   = "".join(f'<div class="stat-chip"><span>{k}</span><strong>{v}건</strong></div>' for k, v in status_count.items())
best_rows     = "".join(f'<li><span class="rank">{i+1}</span><span class="pname">{b[0]}</span><span class="qty">{b[1]}개</span></li>' for i, b in enumerate(bestsellers))

# Monthly sales (last 12 months)
monthly_sales = defaultdict(float)
for o in orders_all:
    ym = o["order_date"][:7]
    monthly_sales[ym] += float(o["actual_order_amount"]["order_price_amount"])
monthly_sorted = sorted(monthly_sales.items())[-12:]
monthly_labels = json.dumps([m[0] for m in monthly_sorted], ensure_ascii=False)
monthly_data   = json.dumps([round(m[1]) for m in monthly_sorted])

# Weekly sales (this month)
week_sales = defaultdict(float)
for o in orders_month:
    dt2 = datetime.strptime(o["order_date"][:10], "%Y-%m-%d")
    week_start = (dt2 - timedelta(days=dt2.weekday())).strftime("%m/%d")
    week_sales[week_start] += float(o["actual_order_amount"]["order_price_amount"])
weekly_sorted = sorted(week_sales.items())
weekly_labels = json.dumps([w[0] for w in weekly_sorted], ensure_ascii=False)
weekly_data   = json.dumps([round(w[1]) for w in weekly_sorted])

# Product revenue this month (qty * price)
price_map = {p["product_name"]: int(float(p.get("price","0"))) for p in real_products}
prod_rev  = {name: qty * price_map.get(name,0) for name,qty in product_sales.items() if price_map.get(name,0)>0}
prod_rev_sorted = sorted(prod_rev.items(), key=lambda x: -x[1])
rev_labels = json.dumps([r[0] for r in prod_rev_sorted], ensure_ascii=False)
rev_data   = json.dumps([r[1] for r in prod_rev_sorted])

# This month qty per product (for profit KPI)
month_qty_json = json.dumps(dict(product_sales), ensure_ascii=False)

# ── HTML ─────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>papier archive</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Apple SD Gothic Neo',sans-serif;background:#f5f5f5;color:#222;font-size:14px}}
/* Login */
.login-wrap{{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#111}}
.login-card{{background:#fff;border-radius:16px;padding:48px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.4)}}
.login-card h1{{font-size:20px;font-weight:300;letter-spacing:4px;text-align:center;margin-bottom:6px}}
.login-card p{{font-size:11px;color:#aaa;text-align:center;margin-bottom:32px}}
.lf{{margin-bottom:14px}}
.lf label{{font-size:11px;color:#888;display:block;margin-bottom:5px}}
.lf input{{width:100%;border:1px solid #ddd;border-radius:8px;padding:10px 12px;font-size:13px;outline:none;font-family:inherit}}
.lf input:focus{{border-color:#111}}
.login-btn{{width:100%;background:#111;color:#fff;border:none;border-radius:8px;padding:12px;font-size:13px;cursor:pointer;margin-top:6px;font-family:inherit}}
.login-btn:hover{{background:#333}}
.login-err{{font-size:12px;color:#e53;text-align:center;margin-top:10px;min-height:16px}}
/* App */
#app{{display:none}}
.app{{display:flex;min-height:100vh}}
.sidebar{{width:176px;background:#111;color:#fff;flex-shrink:0;display:flex;flex-direction:column;position:fixed;top:0;left:0;height:100vh}}
.sidebar .logo{{padding:22px 18px 14px;font-size:13px;letter-spacing:3px;font-weight:300;border-bottom:1px solid #1e1e1e}}
.sidebar .logo span{{font-size:10px;color:#555;display:block;margin-top:3px;letter-spacing:1px}}
.sidebar nav{{flex:1;padding:12px 0}}
.sidebar nav a{{display:flex;align-items:center;gap:10px;padding:11px 18px;font-size:12px;color:#888;cursor:pointer;border-left:3px solid transparent;transition:all .15s}}
.sidebar nav a:hover{{color:#fff;background:rgba(255,255,255,.04)}}
.sidebar nav a.active{{color:#fff;border-left-color:#fff;background:rgba(255,255,255,.07)}}
.sidebar nav a .ic{{width:18px;text-align:center;font-size:14px}}
.sidebar .logout{{padding:16px 18px;border-top:1px solid #1e1e1e}}
.sidebar .logout button{{width:100%;background:transparent;color:#555;border:1px solid #2a2a2a;border-radius:6px;padding:7px;font-size:11px;cursor:pointer;font-family:inherit}}
.sidebar .logout button:hover{{color:#fff;border-color:#555}}
.main{{flex:1;margin-left:176px;background:#f5f5f5;min-height:100vh}}
.topbar{{background:#fff;border-bottom:1px solid #eee;padding:12px 28px;font-size:11px;color:#aaa}}
.page{{display:none;padding:24px 28px}}
.page.active{{display:block}}
/* KPI */
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:20px}}
.kpi{{background:#fff;border-radius:10px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.kpi .lbl{{font-size:11px;color:#999;margin-bottom:7px}}
.kpi .val{{font-size:24px;font-weight:700;color:#111}}
.kpi .sub{{font-size:11px;color:#bbb;margin-top:3px}}
/* Cards */
.grid2{{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:20px}}
.grid2b{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}}
.card{{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.card h3{{font-size:13px;font-weight:600;color:#555;margin-bottom:16px;letter-spacing:.5px}}
.stat-chips{{display:flex;flex-wrap:wrap;gap:8px}}
.stat-chip{{background:#f8f8f8;border-radius:7px;padding:8px 14px;display:flex;flex-direction:column;gap:3px}}
.stat-chip span{{font-size:10px;color:#aaa}}
.stat-chip strong{{font-size:16px;font-weight:700}}
ol.blist{{list-style:none}}
ol.blist li{{display:flex;align-items:center;padding:9px 0;border-bottom:1px solid #f5f5f5;gap:10px}}
.rank{{font-size:11px;font-weight:700;color:#ccc;width:18px;text-align:center}}
li:nth-child(1) .rank{{color:#f0c040}}
li:nth-child(2) .rank{{color:#aaa}}
li:nth-child(3) .rank{{color:#c87533}}
.pname{{flex:1;font-size:12px}}
.qty{{font-size:12px;font-weight:600;color:#666}}
canvas{{max-height:200px}}
.chart-btn{{background:#f0f0f0;border:none;border-radius:5px;padding:4px 10px;font-size:11px;cursor:pointer;font-family:inherit;color:#888;transition:all .15s}}
.chart-btn.active{{background:#111;color:#fff}}
.chart-btn:hover:not(.active){{background:#ddd}}
/* Calendar */
.cal-wrap{{width:100%}}
.cal-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}}
.cal-header h2{{font-size:18px;font-weight:700;color:#111}}
.cal-nav{{background:none;border:1px solid #e0e0e0;border-radius:7px;padding:5px 14px;cursor:pointer;font-size:16px;color:#555;font-family:inherit;transition:background .12s}}
.cal-nav:hover{{background:#f5f5f5}}
.cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}}
.cal-dh{{text-align:center;font-size:11px;font-weight:600;color:#bbb;padding:4px 0;margin-bottom:2px}}
.cal-dh:first-child{{color:#e07070}}.cal-dh:last-child{{color:#6090e0}}
.cal-day{{min-height:70px;border:1px solid #f0f0f0;border-radius:9px;padding:7px;cursor:pointer;transition:background .12s;position:relative;background:#fff}}
.cal-day:hover{{background:#f8f8f8}}
.cal-day.selected{{border-color:#111;background:#f2f2f2}}
.cal-day.today .cal-dn{{background:#111;color:#fff;border-radius:50%}}
.cal-day.other-m{{opacity:.3;pointer-events:none}}
.cal-day.sun .cal-dn{{color:#e07070}}.cal-day.sat .cal-dn{{color:#6090e0}}
.cal-day.today.sun .cal-dn,.cal-day.today.sat .cal-dn{{color:#fff}}
.cal-dn{{font-size:12px;font-weight:600;width:22px;height:22px;display:flex;align-items:center;justify-content:center;margin-bottom:4px}}
.cal-dots{{display:flex;flex-wrap:wrap;gap:2px}}
.cal-dot{{width:6px;height:6px;border-radius:50%;background:#aaa}}
.cal-dot.판매행사{{background:#4caf50}}.cal-dot.발주{{background:#ff9800}}
.cal-dot.미팅{{background:#2196f3}}.cal-dot.기타{{background:#9e9e9e}}
/* Event section */
.evt-section{{background:#fff;border-radius:10px;padding:20px 24px;box-shadow:0 1px 3px rgba(0,0,0,.07);margin-top:14px}}
.evt-sec-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}}
.evt-sec-head h3{{font-size:13px;font-weight:600;color:#555}}
.evt-card{{border:1px solid #f0f0f0;border-radius:8px;padding:12px 14px;margin-bottom:8px;display:flex;gap:12px;align-items:flex-start}}
.evt-badge{{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600;white-space:nowrap;margin-top:2px;flex-shrink:0}}
.evt-badge.판매행사{{background:#e8f5e9;color:#2e7d32}}.evt-badge.발주{{background:#fff3e0;color:#e65100}}
.evt-badge.미팅{{background:#e3f2fd;color:#1565c0}}.evt-badge.기타{{background:#f5f5f5;color:#757575}}
.evt-body{{flex:1;min-width:0}}
.evt-title{{font-size:13px;font-weight:600;color:#111;margin-bottom:3px}}
.evt-meta{{font-size:11px;color:#aaa;margin-bottom:4px}}
.evt-detail{{font-size:12px;color:#666;white-space:pre-wrap}}
.evt-del{{background:none;border:none;color:#ccc;cursor:pointer;font-size:18px;padding:0 4px;line-height:1;flex-shrink:0}}
.evt-del:hover{{color:#e53}}
/* Split layout */
.split{{display:grid;grid-template-columns:260px 1fr;gap:14px;min-height:calc(100vh - 160px)}}
.list-panel{{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);overflow:hidden;display:flex;flex-direction:column}}
.panel-head{{padding:14px 18px;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}}
.panel-head h3{{font-size:12px;font-weight:600;color:#555}}
.list-scroll{{overflow-y:auto;flex:1}}
.li{{padding:12px 18px;border-bottom:1px solid #f8f8f8;cursor:pointer;transition:background .12s}}
.li:hover{{background:#fafafa}}
.li.active{{background:#f2f2f2;font-weight:600}}
.li .nm{{font-size:13px;color:#222}}
.li .sub{{font-size:11px;color:#bbb;margin-top:2px}}
.detail{{background:#fff;border-radius:10px;padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.07);overflow-y:auto}}
.detail-empty{{display:flex;align-items:center;justify-content:center;color:#ccc;font-size:13px;min-height:300px}}
/* Forms */
.fg{{margin-bottom:16px}}
.fg label{{font-size:11px;color:#888;display:block;margin-bottom:5px;font-weight:500}}
.fg input,.fg textarea,.fg select{{width:100%;border:1px solid #e0e0e0;border-radius:7px;padding:8px 10px;font-size:13px;outline:none;font-family:inherit}}
.fg input:focus,.fg textarea:focus{{border-color:#111}}
.fg textarea{{resize:vertical;min-height:72px}}
.frow{{display:grid;gap:12px}}
.frow.c2{{grid-template-columns:1fr 1fr}}
.frow.c3{{grid-template-columns:1fr 1fr 1fr}}
/* Dyn table */
.dtbl{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:6px}}
.dtbl th{{font-size:11px;color:#bbb;font-weight:500;padding:5px 6px;border-bottom:1px solid #eee;text-align:left;white-space:nowrap}}
.dtbl td{{padding:3px 3px;vertical-align:middle}}
.dtbl td input{{border:1px solid #e0e0e0;border-radius:5px;padding:4px 7px;font-size:12px;width:100%;outline:none;font-family:inherit}}
.dtbl td input:focus{{border-color:#111}}
.del-btn{{background:none;border:none;color:#ccc;cursor:pointer;font-size:16px;line-height:1;padding:0 4px}}
.del-btn:hover{{color:#e53}}
.add-btn{{width:100%;background:none;border:1px dashed #ddd;border-radius:6px;padding:6px;font-size:12px;color:#aaa;cursor:pointer;font-family:inherit}}
.add-btn:hover{{border-color:#888;color:#555}}
/* Buttons */
.btn{{border:none;border-radius:7px;padding:9px 18px;font-size:12px;cursor:pointer;font-family:inherit}}
.btn-p{{background:#111;color:#fff}}
.btn-p:hover{{background:#333}}
.btn-p:disabled{{background:#bbb;cursor:default}}
.btn-d{{background:#fff0f0;color:#e53;border:1px solid #fcc}}
.btn-d:hover{{background:#ffe0e0}}
.btn-g{{background:#f5f5f5;color:#555;border:1px solid #e8e8e8}}
.btn-g:hover{{background:#eee}}
.btn-row{{display:flex;gap:8px;margin-top:18px;align-items:center}}
.save-st{{font-size:11px;color:#aaa}}
/* Stock */
.qtbl{{width:100%;border-collapse:collapse;font-size:12px}}
.qtbl th{{text-align:left;padding:8px 10px;border-bottom:2px solid #eee;color:#aaa;font-weight:500}}
.qtbl td{{padding:8px 10px;border-bottom:1px solid #f5f5f5;vertical-align:middle}}
.qty-inp{{width:66px;border:1px solid #ddd;border-radius:5px;padding:3px 7px;font-size:12px;text-align:right;outline:none}}
.qty-inp:focus{{border-color:#111}}
/* Sortable header */
.sh{{cursor:pointer;user-select:none;white-space:nowrap}}
.sh:hover{{color:#555}}
.sh .arr{{font-size:9px;margin-left:2px;color:#888}}
/* Cost summary */
.csum{{background:#f8f8f8;border-radius:8px;padding:14px;margin-top:12px}}
.csum .cr{{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;color:#666}}
.csum .cr.tot{{border-top:1px solid #e0e0e0;margin-top:8px;padding-top:10px;font-weight:700;font-size:14px;color:#111}}
.csum .cr.mgn{{font-size:13px;font-weight:600;color:#2a7}}
.csum .cr.mgn.neg{{color:#e53}}
/* Part search modal */
.modal-bg{{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center;display:none}}
.modal-bg.open{{display:flex}}
.modal-box{{background:#fff;border-radius:12px;width:520px;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 40px rgba(0,0,0,.2)}}
.modal-head{{padding:16px 20px;border-bottom:1px solid #eee;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}}
.modal-head h4{{font-size:14px;font-weight:600;color:#222}}
.modal-close{{background:none;border:none;font-size:20px;color:#aaa;cursor:pointer;line-height:1;padding:2px 6px}}
.modal-close:hover{{color:#333}}
.modal-srch{{padding:12px 16px;border-bottom:1px solid #f0f0f0;flex-shrink:0}}
.modal-srch input{{width:100%;border:1px solid #e0e0e0;border-radius:7px;padding:8px 12px;font-size:13px;outline:none;font-family:inherit}}
.modal-srch input:focus{{border-color:#111}}
.modal-body{{overflow-y:auto;flex:1;padding:8px 0;min-height:120px}}
.mitem{{padding:10px 16px;cursor:pointer;border-bottom:1px solid #f8f8f8;transition:background .1s}}
.mitem:hover{{background:#f5f5f5}}
.mitem .mn{{font-size:13px;color:#222;font-weight:500}}
.mitem .ms{{font-size:11px;color:#aaa;margin-top:2px}}
</style>
</head>
<body>

<!-- LOGIN -->
<div id="login-screen" class="login-wrap">
  <div class="login-card">
    <h1>papier archive</h1>
    <p>관리자 페이지</p>
    <div class="lf"><label>아이디</label>
      <input type="text" id="lu" placeholder="아이디" onkeydown="if(event.key==='Enter')login()">
    </div>
    <div class="lf"><label>비밀번호</label>
      <input type="password" id="lp" placeholder="비밀번호" onkeydown="if(event.key==='Enter')login()">
    </div>
    <button class="login-btn" onclick="login()">로그인</button>
    <div class="login-err" id="lerr"></div>
  </div>
</div>

<!-- APP -->
<div id="app">
<div class="app">
  <div class="sidebar">
    <div class="logo">papier archive<span>ADMIN</span></div>
    <nav>
      <a id="nav-main"      class="active" onclick="showPage('main')">     <span class="ic">📊</span>대시보드</a>
      <a id="nav-costs"                    onclick="showPage('costs')">    <span class="ic">🧮</span>원가 계산</a>
      <a id="nav-bom"                      onclick="showPage('bom')">      <span class="ic">📋</span>BOM</a>
      <a id="nav-suppliers"                onclick="showPage('suppliers')"><span class="ic">🏢</span>거래 업체</a>
      <a id="nav-schedule"                 onclick="showPage('schedule')"> <span class="ic">📅</span>일정</a>
    </nav>
    <div class="logout"><button onclick="logout()">로그아웃</button></div>
  </div>

  <div class="main">
    <div class="topbar">{now_str}</div>

    <!-- 대시보드 -->
    <div class="page active" id="page-main">
      <div class="kpi-grid">
        <div class="kpi"><div class="lbl">누적 총 매출</div><div class="val">{int(total_all):,}원</div><div class="sub">전체 기간 · {order_count_all}건</div></div>
        <div class="kpi"><div class="lbl">이번달 총 매출</div><div class="val">{int(total_month):,}원</div><div class="sub">{month_start} ~ {today} · {order_count}건</div></div>
        <div class="kpi"><div class="lbl">오늘 매출</div><div class="val">{int(total_today):,}원</div><div class="sub">{today}</div></div>
        <div class="kpi"><div class="lbl">재고 부족 상품</div><div class="val" id="low-kpi" style="color:#bbb">-</div><div class="sub">잔여 5개 이하</div></div>
        <div class="kpi"><div class="lbl">이번달 예상 순수익</div><div class="val" id="profit-kpi" style="color:#bbb">-</div><div class="sub">원가계산 × 판매수량</div></div>
      </div>
      <div class="grid2">
        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
            <h3 style="margin-bottom:0">매출 추이</h3>
            <div style="display:flex;gap:4px">
              <button class="chart-btn active" onclick="switchSalesChart('day',this)">일별</button>
              <button class="chart-btn" onclick="switchSalesChart('week',this)">주별</button>
              <button class="chart-btn" onclick="switchSalesChart('month',this)">월별</button>
            </div>
          </div>
          <canvas id="salesChart"></canvas>
        </div>
        <div class="card"><h3>주문 처리 현황</h3><div class="stat-chips">{status_rows}</div><br><canvas id="statusChart"></canvas></div>
      </div>
      <div class="grid2b">
        <div class="card"><h3>상품별 매출 비중 (이번달)</h3><canvas id="prodRevenueChart" style="max-height:220px"></canvas></div>
        <div class="card"><h3>상품별 판매량 순위 (이번달)</h3><canvas id="prodSalesChart" style="max-height:220px"></canvas></div>
      </div>
      <div class="grid2b">
        <div class="card"><h3>베스트셀러 (이번달)</h3><ol class="blist">{best_rows}</ol></div>
        <div class="card">
          <h3>재고 관리</h3>
          <table class="qtbl"><thead><tr><th>상품명</th><th>옵션</th><th>기초재고</th><th>판매수량</th><th>잔여재고</th></tr></thead>
            <tbody id="stock-tbody"><tr><td colspan="5" style="padding:16px;color:#ccc;text-align:center">불러오는 중...</td></tr></tbody>
          </table>
          <div class="btn-row">
            <button class="btn btn-p" id="save-btn" onclick="saveStock()">저장</button>
            <span class="save-st" id="stock-st"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 원가 계산 -->
    <div class="page" id="page-costs">
      <div class="split">
        <div class="list-panel">
          <div class="panel-head"><h3>상품 목록</h3></div>
          <div class="list-scroll" id="costs-list"></div>
        </div>
        <div class="detail" id="costs-detail"><div class="detail-empty">상품을 선택하세요</div></div>
      </div>
    </div>

    <!-- BOM -->
    <div class="page" id="page-bom">
      <div style="background:#fff;border-radius:10px;padding:12px 18px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.07);display:flex;align-items:center;gap:14px">
        <span style="font-size:12px;color:#888;font-weight:500;white-space:nowrap">거래처 필터</span>
        <select id="bom-filter-sup" onchange="onBomFilter()" style="border:1px solid #e0e0e0;border-radius:6px;padding:6px 10px;font-size:12px;outline:none;font-family:inherit;min-width:140px">
          <option value="">전체</option>
        </select>
        <span style="font-size:11px;color:#bbb">거래처를 선택하면 해당 거래처 부품 전체를 볼 수 있습니다</span>
      </div>
      <div class="split">
        <div class="list-panel">
          <div class="panel-head"><h3>상품 목록</h3></div>
          <div class="list-scroll" id="bom-list"></div>
        </div>
        <div class="detail" id="bom-detail"><div class="detail-empty">상품을 선택하거나 거래처로 필터링하세요</div></div>
      </div>
    </div>

    <!-- 거래 업체 -->
    <div class="page" id="page-suppliers">
      <div class="split">
        <div class="list-panel">
          <div class="panel-head">
            <h3>거래 업체</h3>
            <button class="btn btn-g" style="padding:5px 10px;font-size:11px" onclick="addSupplier()">+ 추가</button>
          </div>
          <div class="list-scroll" id="sup-list"></div>
        </div>
        <div class="detail" id="sup-detail"><div class="detail-empty">업체를 선택하거나 추가하세요</div></div>
      </div>
    </div>

    <!-- 일정 -->
    <div class="page" id="page-schedule" style="padding:6px 24px 24px">
      <div class="cal-wrap">
        <div style="background:#fff;border-radius:10px;padding:20px 24px;box-shadow:0 1px 3px rgba(0,0,0,.07)">
          <div class="cal-header">
            <button class="cal-nav" onclick="calMove(-1)">&#8249;</button>
            <h2 id="cal-title"></h2>
            <button class="cal-nav" onclick="calMove(1)">&#8250;</button>
          </div>
          <div class="cal-grid" id="cal-grid"></div>
        </div>
        <div class="evt-section">
          <div class="evt-sec-head">
            <h3 id="evt-date-title">날짜를 선택하세요</h3>
            <button class="btn btn-p" id="add-evt-btn" onclick="openSchModal()" style="display:none;padding:6px 12px;font-size:12px">+ 일정 추가</button>
          </div>
          <div id="evt-list"><div style="color:#ccc;font-size:13px;text-align:center;padding:28px 0">날짜를 클릭하면 일정을 확인할 수 있어요</div></div>
        </div>
      </div>
    </div>

  </div>
</div>
</div>

<!-- 일정 추가 모달 -->
<div id="sch-modal" class="modal-bg" onclick="if(event.target===this)closeSchModal()" style="display:none">
  <div class="modal-box" style="max-width:440px;padding:0">
    <div class="modal-head"><h4>일정 추가</h4><button class="modal-close" onclick="closeSchModal()">×</button></div>
    <div style="padding:20px">
      <div class="fg"><label>제목 *</label><input type="text" id="sch-title" placeholder="일정 제목을 입력하세요"></div>
      <div class="frow c2">
        <div class="fg"><label>날짜 *</label><input type="date" id="sch-date"></div>
        <div class="fg"><label>시간</label><input type="time" id="sch-time"></div>
      </div>
      <div class="fg"><label>장소</label><input type="text" id="sch-loc" placeholder="장소 (선택)"></div>
      <div class="fg"><label>구분</label>
        <select id="sch-type" style="width:100%;border:1px solid #e0e0e0;border-radius:7px;padding:8px 10px;font-size:13px;outline:none;font-family:inherit">
          <option>판매행사</option><option>발주</option><option>미팅</option><option>기타</option>
        </select>
      </div>
      <div class="fg"><label>상세내용</label><textarea id="sch-detail" placeholder="상세 내용 (선택)" style="min-height:80px"></textarea></div>
      <div class="btn-row" style="margin-top:4px">
        <button class="btn btn-g" onclick="closeSchModal()">취소</button>
        <button class="btn btn-p" onclick="saveSchEvent()">추가</button>
        <span id="sch-st" class="save-st"></span>
      </div>
    </div>
  </div>
</div>

<!-- 부품 검색 모달 -->
<div id="part-modal" class="modal-bg" onclick="if(event.target===this)closePartModal()">
  <div class="modal-box">
    <div class="modal-head">
      <h4>거래처 자재 검색</h4>
      <button class="modal-close" onclick="closePartModal()">×</button>
    </div>
    <div class="modal-srch">
      <input type="text" id="part-q" placeholder="자재명 또는 업체명 검색..." oninput="renderPartSearch(this.value)">
    </div>
    <div class="modal-body" id="part-results"></div>
  </div>
</div>

<script>
// ── Auth ─────────────────────────────────────
const UH = '{user_hash}', PH = '{pass_hash}';
async function sha256(s) {{
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
}}
async function login() {{
  const errEl = document.getElementById('lerr');
  try {{
    const u=document.getElementById('lu').value.trim(), p=document.getElementById('lp').value;
    if(!u||!p) {{ errEl.textContent='아이디와 비밀번호를 입력하세요.'; return; }}
    errEl.textContent='확인 중...';
    const [uh,ph] = await Promise.all([sha256(u),sha256(p)]);
    if(uh===UH&&ph===PH) {{
      sessionStorage.setItem('auth','1');
      document.getElementById('login-screen').style.display='none';
      document.getElementById('app').style.display='block';
      initApp();
    }} else {{ errEl.textContent='아이디 또는 비밀번호가 틀렸습니다.'; }}
  }} catch(e) {{ errEl.textContent='오류: '+e.message; }}
}}
function logout() {{ sessionStorage.removeItem('auth'); location.reload(); }}
window.addEventListener('DOMContentLoaded', ()=>{{
  if(sessionStorage.getItem('auth')==='1') {{
    document.getElementById('login-screen').style.display='none';
    document.getElementById('app').style.display='block';
    initApp();
  }}
}});

// ── Navigation ───────────────────────────────
function showPage(n) {{
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.sidebar nav a').forEach(a=>a.classList.remove('active'));
  document.getElementById('page-'+n).classList.add('active');
  document.getElementById('nav-'+n).classList.add('active');
}}

// ── GitHub API ───────────────────────────────
const GH_OWNER='rlaqkqehfdl1-ship-it', GH_REPO_='papier-dashboard';
function getToken() {{
  const _a='{pat_a}',_b='{pat_b}';
  if(_a&&_b) return atob(_a+_b);
  let t=localStorage.getItem('gh_token');
  if(!t) {{ t=prompt('GitHub Personal Access Token'); if(t) localStorage.setItem('gh_token',t.trim()); }}
  return t||'';
}}
async function ghGet(f) {{
  const tok=getToken();
  const hdrs={{'Accept':'application/vnd.github+json'}};
  if(tok) hdrs['Authorization']='Bearer '+tok;
  const r=await fetch(
    `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO_}}/contents/${{f}}?_=${{Date.now()}}`,
    {{cache:'no-store',headers:hdrs}});
  if(!r.ok) return {{sha:null,data:null}};
  const m=await r.json();
  const bin=atob(m.content.replace(/\\n/g,''));
  const bytes=Uint8Array.from(bin,c=>c.charCodeAt(0));
  return {{sha:m.sha,data:JSON.parse(new TextDecoder('utf-8').decode(bytes))}};
}}
async function ghPut(f,data,msg) {{
  const tok=getToken(); if(!tok) throw new Error('토큰 없음');
  // 저장 직전 항상 최신 SHA를 가져와서 stale-SHA 오류 원천 차단
  const {{sha}}=await ghGet(f);
  const text=JSON.stringify(data,null,2);
  const eb=new TextEncoder().encode(text);
  let bin=''; eb.forEach(b=>bin+=String.fromCharCode(b));
  const body={{message:msg,content:btoa(bin)}}; if(sha) body.sha=sha;
  const r=await fetch(`https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO_}}/contents/${{f}}`,{{
    method:'PUT', headers:{{'Authorization':`Bearer ${{tok}}`,'Content-Type':'application/json','Accept':'application/vnd.github+json'}},
    body:JSON.stringify(body)
  }});
  if(!r.ok) throw new Error((await r.json()).message);
}}

// ── Init ─────────────────────────────────────
function initApp() {{
  initCharts(); loadStock(); initCosts(); initBom(); initSuppliers(); initSchedule();
}}

// ── 재고 ─────────────────────────────────────
const SOLD={sold_json};
let stockData=null;
async function loadStock() {{
  const {{data}}=await ghGet('stock.json');
  if(!data) return;
  stockData=data; renderStock();
}}
function rc(r){{ return r<=0?'#e53':r<=5?'#e96':'#2a7'; }}
function renderStock() {{
  if(!stockData) return;
  let html='', prev=null, low=0;
  stockData.products.forEach((p,pi)=>{{
    const sold=SOLD[p.product_name]||0;
    p.variants.forEach((v,vi)=>{{
      const base=v.base_qty??v.qty??0, rem=base-sold;
      if(rem<=5) low++;
      const sn=prev!==p.product_name; prev=p.product_name;
      html+=`<tr>
        ${{sn?`<td style="padding:8px 10px;border-bottom:1px solid #f5f5f5;font-weight:600;font-size:12px">${{p.product_name}}</td>`:'<td style="padding:8px 10px;border-bottom:1px solid #f5f5f5"></td>'}}
        <td style="padding:8px 10px;border-bottom:1px solid #f5f5f5;color:#888;font-size:11px">${{v.option}}</td>
        <td style="padding:8px 10px;border-bottom:1px solid #f5f5f5"><input class="qty-inp" type="number" min="0" value="${{base}}" data-pi="${{pi}}" data-vi="${{vi}}" data-s="${{sold}}" onchange="onBC(this)"></td>
        <td style="padding:8px 10px;border-bottom:1px solid #f5f5f5;color:#aaa;font-size:12px">${{sold}}개</td>
        <td id="r-${{pi}}-${{vi}}" style="padding:8px 10px;border-bottom:1px solid #f5f5f5;font-weight:700;color:${{rc(rem)}};font-size:12px">${{rem}}개</td>
      </tr>`;
    }});
  }});
  document.getElementById('stock-tbody').innerHTML=html;
  const k=document.getElementById('low-kpi');
  if(k){{ k.textContent=low+'개'; k.style.color=low>0?'#e53':'#2a7'; }}
  document.getElementById('stock-st').textContent=`저장: ${{stockData.updated_at||'-'}} · 판매수량 매일 10시 갱신`;
}}
function onBC(inp) {{
  const base=parseInt(inp.value)||0,sold=parseInt(inp.dataset.s)||0,rem=base-sold;
  const el=document.getElementById(`r-${{inp.dataset.pi}}-${{inp.dataset.vi}}`);
  el.textContent=rem+'개'; el.style.color=rc(rem);
}}
async function saveStock() {{
  document.querySelectorAll('.qty-inp').forEach(inp=>{{
    const p=stockData.products[inp.dataset.pi],v=p.variants[inp.dataset.vi];
    v.base_qty=parseInt(inp.value)||0; delete v.qty;
  }});
  stockData.updated_at=new Date().toISOString().slice(0,10);
  const btn=document.getElementById('save-btn');
  btn.disabled=true; btn.textContent='저장 중...';
  try {{
    await ghPut('stock.json',stockData,`재고 업데이트 ${{stockData.updated_at}}`);
    document.getElementById('stock-st').textContent=`저장: ${{stockData.updated_at}}`;
  }} catch(e) {{ alert('저장 실패: '+e.message); }}
  btn.disabled=false; btn.textContent='저장';
}}

// ── 원가 계산 ─────────────────────────────────
const PRODS={product_names_json};
const PRICES={product_prices_json};
let costData=null, selCost=null;
async function initCosts() {{
  const {{data}}=await ghGet('costs.json');
  costData=data||{{updated_at:'',products:{{}}}};
  renderCostList();
  updateProfitKpi();
}}
function renderCostList() {{
  document.getElementById('costs-list').innerHTML=PRODS.map((n,i)=>{{
    const c=costData.products[n];
    let sub='';
    if(c&&c.consumer_price) {{
      const cp=c.consumer_price, p7=Math.round(cp*0.93);
      const bomT=((bomData&&bomData.bom&&bomData.bom[n])||[]).reduce((s,p)=>s+(p['수량']||0)*(p['가격']||0),0);
      const itT=(c.items||[]).reduce((s,it)=>s+(it.qty||0)*(it.unit_price||0),0);
      const fee7=Math.round(p7*0.019), ship=c.shipping||0;
      const cr=p7>0?((bomT+itT+ship+fee7)/p7*100).toFixed(2):0;
      sub=`<div class="sub">소비자가 ${{cp.toLocaleString()}}원 · 원가율 ${{cr}}%</div>`;
    }}
    return `<div class="li${{selCost===n?' active':''}}" data-idx="${{i}}" onclick="selCostProd(this.dataset.idx)"><div class="nm">${{n}}</div>${{sub}}</div>`;
  }}).join('');
}}
function selCostProd(idx) {{ const n=PRODS[idx]; selCost=n; renderCostList(); renderCostDetail(n); }}
function renderCostDetail(n) {{
  const d=document.getElementById('costs-detail');
  const c=costData.products[n]||{{}};
  const bomParts=(bomData&&bomData.bom&&bomData.bom[n])||[];
  c.materials=bomParts.map(p=>({{'name':p['부품명']||'','qty':p['수량']||1,'unit':'개','unit_price':p['가격']||0}}));
  const saved=c.items||[];
  while(saved.length<9) saved.push({{'name':'','supplier':'','qty':0,'unit_price':0,'spec':''}});
  const editRows=saved.slice(0,9).map((it,i)=>`
    <tr>
      <td style="width:18px;text-align:center;color:#ccc;font-size:10px;padding:2px 3px">${{i+2}}</td>
      <td><input type="text" value="${{(it.name||'').replace(/"/g,'&quot;')}}" placeholder="항목명" oninput="updCS()"></td>
      <td><input type="text" value="${{(it.supplier||'').replace(/"/g,'&quot;')}}" placeholder="업체명" oninput="updCS()"></td>
      <td><input type="number" value="${{it.qty||0}}" min="0" step="1" style="width:52px" oninput="updCS()"></td>
      <td><input type="number" value="${{it.unit_price||0}}" min="0" style="width:68px" oninput="updCS()"></td>
      <td><input type="text" value="${{(it.spec||'').replace(/"/g,'&quot;')}}" placeholder="사양" oninput="updCS()"></td>
      <td class="isum" style="text-align:right;font-size:11px;color:#aaa;padding:2px 6px;white-space:nowrap">0원</td>
    </tr>`).join('');
  const itemRows=`<tr id="bom-ref-row" style="background:#eef3ee;pointer-events:none;user-select:none">
      <td style="width:18px;text-align:center;color:#bbb;font-size:10px;padding:2px 3px">1</td>
      <td style="padding:2px 4px;font-size:12px;color:#4a7a4a;font-weight:600">순수자재비</td>
      <td style="padding:2px 4px;font-size:11px;color:#888">BOM참고</td>
      <td style="padding:2px 4px;font-size:11px;color:#888;text-align:center">1</td>
      <td style="padding:2px 4px;font-size:11px;color:#bbb;text-align:right">-</td>
      <td style="padding:2px 4px;font-size:11px;color:#888">BOM참고</td>
      <td id="bom-sum-row" style="text-align:right;font-size:11px;font-weight:600;color:#4a7a4a;padding:2px 6px;white-space:nowrap">0원</td>
    </tr>`+editRows;
  d.innerHTML=`
    <h3 style="font-size:15px;margin-bottom:12px">${{n}}</h3>
    <div class="fg"><label>재료비 <span style="font-size:10px;color:#bbb;font-weight:400">· BOM 탭에서 수정하세요</span></label>
      <table class="dtbl"><thead><tr><th>재료명</th><th style="width:55px">수량</th><th style="width:45px">단위</th><th style="width:85px">단가(원)</th><th style="width:75px">합계</th></tr></thead>
        <tbody id="cmat"></tbody>
      </table>
      <div style="text-align:right;font-size:11px;color:#888;padding:4px 0 0">재료비 합계: <strong id="bom-total">0원</strong></div>
    </div>
    <div style="display:flex;gap:12px;margin-top:12px;align-items:stretch">
      <div style="flex:1;overflow-x:auto">
        <table class="dtbl" style="min-width:440px">
          <thead><tr>
            <th style="width:18px"></th>
            <th>항목명</th><th style="min-width:70px">업체명</th>
            <th style="width:52px">수량</th><th style="width:68px">단가(원)</th>
            <th style="min-width:60px">사양</th><th style="width:65px">합계</th>
          </tr></thead>
          <tbody id="citems">${{itemRows}}</tbody>
          <tfoot><tr>
            <td colspan="6" style="text-align:right;font-size:11px;color:#888;padding:4px 6px">항목 합계</td>
            <td style="text-align:right;font-size:12px;font-weight:600;padding:4px 6px;white-space:nowrap" id="items-total">0원</td>
          </tr></tfoot>
        </table>
      </div>
      <div style="min-width:185px;background:#f8f8f8;border-radius:8px;padding:12px 14px;font-size:12px;display:flex;flex-direction:column;gap:7px;flex-shrink:0">
        <div>
          <div style="font-size:10px;color:#999;margin-bottom:3px;font-weight:500">배송비 (원)</div>
          <input type="number" id="c-ship" value="${{c.shipping||0}}" min="0" oninput="updCS()"
            style="width:100%;border:1px solid #e0e0e0;border-radius:5px;padding:5px 8px;font-size:12px;outline:none;font-family:inherit">
        </div>
        <div style="border-top:1px solid #e8e8e8;padding-top:7px">
          <div style="display:flex;justify-content:space-between;padding:2px 0">
            <span style="color:#888">플랫폼수수료 7%</span><span id="c-fee7" style="font-weight:500">0원</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:2px 0">
            <span style="color:#888">플랫폼수수료 15%</span><span id="c-fee15" style="font-weight:500">0원</span>
          </div>
        </div>
        <div style="border-top:1px solid #e8e8e8;padding-top:7px">
          <div style="font-size:10px;color:#999;margin-bottom:3px;font-weight:500">소비자가 (원)</div>
          <input type="number" id="c-cprice" value="${{c.consumer_price||0}}" min="0" oninput="updCS()"
            style="width:100%;border:1px solid #e0e0e0;border-radius:5px;padding:5px 8px;font-size:12px;outline:none;font-family:inherit">
        </div>
        <div style="border-top:1px solid #e8e8e8;padding-top:7px">
          <div style="display:flex;justify-content:space-between;padding:2px 0;font-size:11px"><span style="color:#555">상시 7% 할인가</span><span id="c-p7" style="font-weight:500">0원</span></div>
          <div style="display:flex;justify-content:space-between;padding:2px 0;font-size:11px"><span style="color:#555">10% 할인가</span><span id="c-p10" style="font-weight:500">0원</span></div>
          <div style="display:flex;justify-content:space-between;padding:2px 0;font-size:11px"><span style="color:#555">15% 할인가</span><span id="c-p15" style="font-weight:500">0원</span></div>
          <div style="display:flex;justify-content:space-between;padding:2px 0;font-size:11px"><span style="color:#555">20% 할인가</span><span id="c-p20" style="font-weight:500">0원</span></div>
        </div>
      </div>
    </div>
    <div class="csum" id="csum" style="margin-top:12px"></div>
    <div class="btn-row">
      <button class="btn btn-p" onclick="saveCosts()">저장</button>
      <span class="save-st" id="cost-st"></span>
    </div>`;
  c.materials.forEach(m=>addCMatRow(m));
  updCS();
}}
function addCMatRow(m) {{
  const tb=document.getElementById('cmat'); if(!tb) return;
  const tr=document.createElement('tr');
  tr.dataset.name=m.name||''; tr.dataset.qty=m.qty||0;
  tr.dataset.unit=m.unit||'개'; tr.dataset.price=m.unit_price||0;
  const sub=Math.round((m.qty||0)*(m.unit_price||0));
  tr.innerHTML=`
    <td style="padding:4px 6px;font-size:12px">${{m.name||''}}</td>
    <td style="padding:4px 6px;font-size:12px;text-align:center">${{m.qty||0}}</td>
    <td style="padding:4px 6px;font-size:12px;text-align:center">${{m.unit||'개'}}</td>
    <td style="padding:4px 6px;font-size:12px;text-align:right">${{(m.unit_price||0).toLocaleString()}}</td>
    <td style="padding:4px 6px;font-size:11px;color:#aaa;text-align:right">${{sub.toLocaleString()}}원</td>`;
  tb.appendChild(tr);
}}
function updCS() {{
  let bomT=0;
  document.querySelectorAll('#cmat tr').forEach(tr=>{{
    bomT+=Math.round((parseFloat(tr.dataset.qty)||0)*(parseFloat(tr.dataset.price)||0));
  }});
  const btEl=document.getElementById('bom-total'); if(btEl) btEl.textContent=bomT.toLocaleString()+'원';
  const bsEl=document.getElementById('bom-sum-row'); if(bsEl) bsEl.textContent=bomT.toLocaleString()+'원';
  let itemT=0;
  document.querySelectorAll('#citems tr').forEach(tr=>{{
    if(tr.id==='bom-ref-row') return;
    const ins=tr.querySelectorAll('input'); if(ins.length<4) return;
    const sub=Math.round((parseFloat(ins[2].value)||0)*(parseFloat(ins[3].value)||0));
    itemT+=sub;
    const el=tr.querySelector('.isum'); if(el) el.textContent=sub.toLocaleString()+'원';
  }});
  const totCost=bomT+itemT;
  const itEl=document.getElementById('items-total'); if(itEl) itEl.textContent=totCost.toLocaleString()+'원';
  const ship=parseFloat(document.getElementById('c-ship')?.value)||0;
  const cp=parseFloat(document.getElementById('c-cprice')?.value)||0;
  const p7=Math.round(cp*0.93), p10=Math.round(cp*0.9), p15=Math.round(cp*0.85), p20=Math.round(cp*0.8);
  const fee7=Math.round(p7*0.019);
  const fee15=(selCost==='잔화 [殘 花]'||selCost==='중첩 [重 疊]')?Math.round(p10*0.019):Math.round(cp*0.019);
  const cr=p7>0?((totCost+ship+fee7)/p7*100).toFixed(2):'0';
  const pf7=p7-totCost-ship-fee7, pf15=p15-totCost-ship-fee15;
  const s=(id,v)=>{{const e=document.getElementById(id);if(e)e.textContent=v;}};
  s('c-fee7',fee7.toLocaleString()+'원'); s('c-fee15',fee15.toLocaleString()+'원');
  s('c-p7',p7.toLocaleString()+'원'); s('c-p10',p10.toLocaleString()+'원');
  s('c-p15',p15.toLocaleString()+'원'); s('c-p20',p20.toLocaleString()+'원');
  const el=document.getElementById('csum'); if(!el) return;
  el.innerHTML=`
    <div class="cr"><span>항목 합계 (1~10번)</span><span>${{totCost.toLocaleString()}}원</span></div>
    <div class="cr"><span>배송비</span><span>${{ship.toLocaleString()}}원</span></div>
    <div class="cr"><span>플랫폼수수료 (7%할인 기준)</span><span>${{fee7.toLocaleString()}}원</span></div>
    <div class="cr tot"><span>총 원가 (7%기준)</span><span>${{(totCost+ship+fee7).toLocaleString()}}원</span></div>
    <div class="cr"><span>원가율 (7%할인 기준)</span><span style="font-weight:700">${{cr}}%</span></div>
    <div class="cr mgn${{pf7<0?' neg':''}}"><span>예상순수익 (7% 기준)</span><span>${{pf7.toLocaleString()}}원</span></div>
    <div class="cr mgn${{pf15<0?' neg':''}}"><span>예상 순수익 (15%할인)</span><span>${{pf15.toLocaleString()}}원</span></div>`;
}}
async function saveCosts() {{
  if(!selCost) return;
  const mats=[];
  document.querySelectorAll('#cmat tr').forEach(tr=>{{
    mats.push({{name:tr.dataset.name||'',qty:parseFloat(tr.dataset.qty)||0,
      unit:tr.dataset.unit||'개',unit_price:parseFloat(tr.dataset.price)||0}});
  }});
  const items=[];
  document.querySelectorAll('#citems tr').forEach(tr=>{{
    if(tr.id==='bom-ref-row') return;
    const ins=tr.querySelectorAll('input'); if(ins.length<5) return;
    items.push({{name:ins[0].value,supplier:ins[1].value,
      qty:parseFloat(ins[2].value)||0,unit_price:parseFloat(ins[3].value)||0,spec:ins[4].value}});
  }});
  costData.products[selCost]={{materials:mats,items:items,
    shipping:parseFloat(document.getElementById('c-ship').value)||0,
    consumer_price:parseFloat(document.getElementById('c-cprice').value)||0}};
  costData.updated_at=new Date().toISOString().slice(0,10);
  const st=document.getElementById('cost-st'); st.textContent='저장 중...';
  try {{
    await ghPut('costs.json',costData,'원가 업데이트: '+selCost);
    st.textContent='저장 완료 '+costData.updated_at;
    renderCostList();
  }} catch(e) {{ st.textContent=''; alert('저장 실패: '+e.message); }}
}}

// ── BOM (부품 목록) ───────────────────────────
let bomData=null, curBomProd=null, bomFilter='';
async function initBom() {{
  const {{data}}=await ghGet('bom.json');
  bomData=data||{{updated_at:'',bom:{{}}}};
  renderBomFilter(); renderBomList();
}}
function getAllSuppliers() {{
  const s=new Set();
  Object.values(bomData.bom||{{}}).forEach(parts=>{{
    (parts||[]).forEach(p=>{{ if(p['거래처']) s.add(p['거래처']); }});
  }});
  return [...s].sort();
}}
function renderBomFilter() {{
  const el=document.getElementById('bom-filter-sup'); if(!el) return;
  const cur=el.value;
  el.innerHTML='<option value="">전체</option>'+getAllSuppliers().map(s=>`<option value="${{s}}">${{s}}</option>`).join('');
  el.value=cur;
}}
function onBomFilter() {{
  bomFilter=document.getElementById('bom-filter-sup').value;
  renderBomList();
  if(bomFilter) {{ curBomProd=null; renderBomFilterView(); }}
  else document.getElementById('bom-detail').innerHTML='<div class="detail-empty">상품을 선택하세요</div>';
}}
function renderBomList() {{
  document.getElementById('bom-list').innerHTML=PRODS.map((n,i)=>{{
    const parts=(bomData.bom[n]||[]);
    const matched=bomFilter?parts.filter(p=>p['거래처']===bomFilter):parts;
    if(bomFilter&&!matched.length) return '';
    const sub=`<div class="sub">${{bomFilter?matched.length+'개 매칭':parts.length+'개 부품'}}</div>`;
    return `<div class="li${{curBomProd===n&&!bomFilter?' active':''}}" data-idx="${{i}}" onclick="selBomProd(this.dataset.idx)"><div class="nm">${{n}}</div>${{sub}}</div>`;
  }}).join('');
}}
function selBomProd(idx) {{
  const n=PRODS[idx]; curBomProd=n; bomFilter='';
  document.getElementById('bom-filter-sup').value='';
  renderBomList(); renderBomDetail(n);
}}
function renderBomDetail(n) {{ curBomProd=n;
  const d=document.getElementById('bom-detail');
  const parts=bomData.bom[n]||[];
  d.innerHTML=`
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
      <h3 style="font-size:15px">${{n}}</h3>
      <button class="btn btn-g" style="font-size:11px;padding:5px 12px" onclick="openPartModal()">+ 부품 추가</button>
      <button class="btn btn-g" style="font-size:11px;padding:5px 12px;margin-left:6px" onclick="addBomRow()">직접 입력</button>
    </div>
    <div style="overflow-x:auto">
    <table class="dtbl" style="min-width:680px">
      <thead><tr>
        <th style="min-width:90px">부품명</th>
        <th style="min-width:75px">구매처</th>
        <th style="min-width:75px">거래처</th>
        <th style="min-width:65px">가격(원)</th>
        <th style="min-width:45px">수량</th>
        <th style="min-width:45px">MOQ</th>
        <th style="min-width:75px">옵션</th>
        <th style="min-width:75px">크기</th>
        <th></th>
      </tr></thead>
      <tbody id="bom-tbody"></tbody>
    </table>
    </div>
    <div class="btn-row">
      <button class="btn btn-p" onclick="saveBom()">저장</button>
      <span class="save-st" id="bom-st"></span>
    </div>`;
  (parts).forEach(p=>addBomRowData(p));
}}
function addBomRow() {{
  addBomRowData({{'부품명':'','구매처':'','거래처':'','가격':0,'수량':1,'moq':1,'옵션':'','크기':''}});
}}
function openPartModal() {{
  if(!curBomProd) return;
  document.getElementById('part-modal').classList.add('open');
  document.getElementById('part-q').value='';
  renderPartSearch('');
  setTimeout(()=>document.getElementById('part-q').focus(),60);
}}
function closePartModal() {{
  document.getElementById('part-modal').classList.remove('open');
}}
function renderPartSearch(q) {{
  const sups=(supData&&supData.suppliers)||[];
  const kw=q.trim().toLowerCase();
  let html='';
  sups.forEach((s,si)=>{{
    (s.materials||[]).forEach((m,mi)=>{{
      const nm=(m.name||'').toLowerCase(), sn=(s.name||'').toLowerCase();
      if(kw&&!nm.includes(kw)&&!sn.includes(kw)) return;
      const price=(m.unit_price||0).toLocaleString();
      html+=`<div class="mitem" onclick="addPartFromModal(${{si}},${{mi}})">
        <div class="mn">${{m.name||'(이름 없음)'}}</div>
        <div class="ms">${{s.name||''}}${{m.option?' · '+m.option:''}}${{m.spec?' · '+m.spec:''}} · ${{price}}원${{m.moq>1?' · MOQ '+m.moq:''}}</div>
      </div>`;
    }});
  }});
  if(!html) {{
    if(kw) html='<div style="padding:28px;text-align:center;color:#ccc;font-size:13px">검색 결과 없음</div>';
    else html='<div style="padding:28px;text-align:center;color:#ccc;font-size:13px">등록된 자재 없음<br><span style="font-size:11px">거래 업체 탭에서 먼저 자재를 등록하세요</span></div>';
  }}
  document.getElementById('part-results').innerHTML=html;
}}
function addPartFromModal(si,mi) {{
  const s=supData.suppliers[si], m=s.materials[mi];
  addBomRowData({{'부품명':m.name||'','구매처':m.purchase_source||'','거래처':s.name||'',
    '가격':m.unit_price||0,'수량':1,'moq':m.moq||1,'옵션':m.option||'','크기':m.spec||''}});
  closePartModal();
}}
function addBomRowData(p) {{
  const tb=document.getElementById('bom-tbody'); if(!tb) return;
  const esc=s=>(s||'').replace(/"/g,'&quot;');
  const tr=document.createElement('tr');
  tr.innerHTML=`
    <td><input type="text" value="${{esc(p['부품명'])}}" placeholder="부품명"></td>
    <td><input type="text" value="${{esc(p['구매처'])}}" placeholder="구매처" onchange="renderBomFilter()"></td>
    <td><input type="text" value="${{esc(p['거래처'])}}" placeholder="거래처" onchange="renderBomFilter()"></td>
    <td><input type="number" value="${{p['가격']||0}}" min="0" style="width:65px"></td>
    <td><input type="number" value="${{p['수량']||1}}" min="0" style="width:50px"></td>
    <td><input type="number" value="${{p['moq']||1}}" min="1" style="width:50px"></td>
    <td><input type="text" value="${{esc(p['옵션'])}}" placeholder="옵션"></td>
    <td><input type="text" value="${{esc(p['크기'])}}" placeholder="100x100"></td>
    <td><button class="del-btn" onclick="this.closest('tr').remove()">×</button></td>`;
  tb.appendChild(tr);
}}
function renderBomFilterView() {{
  const d=document.getElementById('bom-detail');
  let html=`<h3 style="font-size:14px;margin-bottom:14px;color:#555">거래처: <strong style="color:#111">${{bomFilter}}</strong></h3>`;
  let found=false;
  PRODS.forEach(n=>{{
    const matched=(bomData.bom[n]||[]).filter(p=>p['거래처']===bomFilter);
    if(!matched.length) return;
    found=true;
    html+=`<div style="font-weight:600;font-size:12px;color:#666;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid #eee">${{n}}</div>
    <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:4px">
      <thead><tr style="color:#aaa">
        <th style="padding:5px 8px;text-align:left;font-weight:500">부품명</th>
        <th style="padding:5px 8px;text-align:left;font-weight:500">구매처</th>
        <th style="padding:5px 8px;text-align:right;font-weight:500">가격</th>
        <th style="padding:5px 8px;text-align:center;font-weight:500">수량</th>
        <th style="padding:5px 8px;text-align:center;font-weight:500">MOQ</th>
        <th style="padding:5px 8px;text-align:left;font-weight:500">옵션</th>
        <th style="padding:5px 8px;text-align:left;font-weight:500">크기</th>
      </tr></thead>
      <tbody>${{matched.map(p=>`<tr style="border-top:1px solid #f5f5f5">
        <td style="padding:6px 8px">${{p['부품명']||''}}</td>
        <td style="padding:6px 8px;color:#888">${{p['구매처']||''}}</td>
        <td style="padding:6px 8px;text-align:right">${{(p['가격']||0).toLocaleString()}}원</td>
        <td style="padding:6px 8px;text-align:center">${{p['수량']||0}}</td>
        <td style="padding:6px 8px;text-align:center">${{p['moq']||0}}</td>
        <td style="padding:6px 8px;color:#888">${{p['옵션']||''}}</td>
        <td style="padding:6px 8px;color:#888">${{p['크기']||''}}</td>
      </tr>`).join('')}}</tbody>
    </table></div>`;
  }});
  if(!found) html+='<div class="detail-empty">해당 거래처의 부품이 없습니다</div>';
  d.innerHTML=html;
}}
async function saveBom() {{
  if(!curBomProd) return;
  const rows=[], tb=document.getElementById('bom-tbody'); if(!tb) return;
  tb.querySelectorAll('tr').forEach(tr=>{{
    const ins=tr.querySelectorAll('input'); if(ins.length<8) return;
    rows.push({{'부품명':ins[0].value,'구매처':ins[1].value,'거래처':ins[2].value,
      '가격':parseFloat(ins[3].value)||0,'수량':parseFloat(ins[4].value)||0,
      'moq':parseFloat(ins[5].value)||0,'옵션':ins[6].value,'크기':ins[7].value}});
  }});
  bomData.bom[curBomProd]=rows;
  bomData.updated_at=new Date().toISOString().slice(0,10);
  const bst=document.getElementById('bom-st'); bst.textContent='저장 중...';
  try {{
    await ghPut('bom.json',bomData,'BOM 업데이트: '+curBomProd);
    bst.textContent='저장 완료 '+bomData.updated_at;
    renderBomFilter(); renderBomList();
  }} catch(e) {{ bst.textContent=''; alert('저장 실패: '+e.message); }}
}}

// ── 거래 업체 ─────────────────────────────────
let supData=null, selSup=null;
async function initSuppliers() {{
  const {{data}}=await ghGet('suppliers.json');
  supData=data||{{updated_at:'',suppliers:[]}};
  renderSupList();
}}
function renderSupList() {{
  const el=document.getElementById('sup-list');
  const sups=supData.suppliers||[];
  el.innerHTML=sups.length?sups.map((s,i)=>`
    <div class="li${{selSup===i?' active':''}}" onclick="selSupplier(${{i}})">
      <div class="nm">${{s.name||'(이름 없음)'}}</div>
      <div class="sub">자재 ${{(s.materials||[]).length}}종 · ${{s.contact||''}}</div>
    </div>`).join('')
    :'<div style="padding:20px;color:#ccc;font-size:12px;text-align:center">등록된 업체가 없습니다</div>';
}}
function addSupplier() {{ selSup=null; renderSupList(); renderSupDetail({{name:'',contact:'',email:'',address:'',note:'',materials:[]}},-1); }}
function selSupplier(i) {{ selSup=i; renderSupList(); renderSupDetail(supData.suppliers[i],i); }}
function renderSupDetail(s,idx) {{
  const d=document.getElementById('sup-detail'), isNew=idx<0;
  d.innerHTML=`
    <h3 style="font-size:15px;margin-bottom:18px">${{isNew?'업체 추가':'업체 정보'}}</h3>
    <div class="frow c2">
      <div class="fg"><label>업체명 *</label><input type="text" id="s-nm" value="${{(s.name||'').replace(/"/g,'&quot;')}}" placeholder="업체명"></div>
      <div class="fg"><label>연락처</label><input type="text" id="s-ct" value="${{(s.contact||'').replace(/"/g,'&quot;')}}" placeholder="010-0000-0000"></div>
    </div>
    <div class="frow c2">
      <div class="fg"><label>이메일</label><input type="text" id="s-em" value="${{(s.email||'').replace(/"/g,'&quot;')}}" placeholder="email@example.com"></div>
      <div class="fg"><label>주소</label><input type="text" id="s-ad" value="${{(s.address||'').replace(/"/g,'&quot;')}}"></div>
    </div>
    <div class="fg"><label>메모</label><textarea id="s-nt" rows="2">${{(s.note||'').replace(/</g,'&lt;')}}</textarea></div>
    <div class="fg" style="margin-top:16px"><label>자재 목록</label>
      <div style="overflow-x:auto">
      <table class="dtbl" style="min-width:700px"><thead><tr>
        <th class="sh" onclick="sortSmat('_bomRef')" style="min-width:90px">BOM 참조<span class="arr" id="ssi-_bomRef"></span></th>
        <th class="sh" onclick="sortSmat('name')">자재명<span class="arr" id="ssi-name"></span></th>
        <th class="sh" onclick="sortSmat('spec')" style="min-width:60px">규격<span class="arr" id="ssi-spec"></span></th>
        <th class="sh" onclick="sortSmat('unit')" style="width:45px">단위<span class="arr" id="ssi-unit"></span></th>
        <th class="sh" onclick="sortSmat('unit_price')" style="width:80px">단가(원)<span class="arr" id="ssi-unit_price"></span></th>
        <th class="sh" onclick="sortSmat('moq')" style="width:55px">MOQ<span class="arr" id="ssi-moq"></span></th>
        <th class="sh" onclick="sortSmat('option')" style="min-width:70px">옵션<span class="arr" id="ssi-option"></span></th>
        <th class="sh" onclick="sortSmat('purchase_source')" style="min-width:80px">구매처<span class="arr" id="ssi-purchase_source"></span></th>
        <th>메모</th><th></th>
      </tr></thead>
        <tbody id="smat"></tbody>
      </table></div>
      <button class="add-btn" onclick="addSMat()">+ 자재 추가</button>
    </div>
    <div class="btn-row">
      <button class="btn btn-p" onclick="saveSup(${{idx}})">저장</button>
      ${{!isNew?`<button class="btn btn-d" onclick="delSup(${{idx}})">삭제</button>`:''}}
      <span class="save-st" id="sup-st"></span>
    </div>`;
  _renderingSupName=s.name||'';
  (s.materials||[]).forEach(m=>addSMatRow(m));
}}
let _renderingSupName='', _supSortCol=null, _supSortDir=1;
function getBomRefs(supName,matName) {{
  if(!bomData||!bomData.bom||!supName||!matName) return '-';
  const refs=PRODS.filter(prod=>(bomData.bom[prod]||[]).some(p=>p['거래처']===supName&&p['부품명']===matName));
  return refs.length?refs.join(', '):'-';
}}
function addSMat() {{ addSMatRow({{name:'',spec:'',unit:'',unit_price:0,moq:1,option:'',purchase_source:'',note:''}}); }}
function addSMatRow(m) {{
  const tb=document.getElementById('smat'); if(!tb) return;
  const esc=s=>(s||'').replace(/"/g,'&quot;');
  const ref=getBomRefs(_renderingSupName,m.name||'');
  const tr=document.createElement('tr');
  tr.innerHTML=`
    <td style="padding:5px 6px;font-size:11px;color:${{ref==='-'?'#ccc':'#555'}};white-space:nowrap;max-width:100px;overflow:hidden;text-overflow:ellipsis" title="${{ref}}">${{ref}}</td>
    <td><input type="text" value="${{esc(m.name)}}" placeholder="자재명" oninput="refreshBomRef(this)"></td>
    <td><input type="text" value="${{esc(m.spec)}}" placeholder="규격/크기"></td>
    <td><input type="text" value="${{esc(m.unit)}}" placeholder="단위" style="width:44px"></td>
    <td><input type="number" value="${{m.unit_price||0}}" min="0" style="width:72px"></td>
    <td><input type="number" value="${{m.moq||1}}" min="1" style="width:48px"></td>
    <td><input type="text" value="${{esc(m.option)}}" placeholder="옵션"></td>
    <td><input type="text" value="${{esc(m.purchase_source)}}" placeholder="구매처"></td>
    <td><input type="text" value="${{esc(m.note)}}" placeholder="메모"></td>
    <td><button class="del-btn" onclick="this.closest('tr').remove()">×</button></td>`;
  tb.appendChild(tr);
}}
function refreshBomRef(inp) {{
  const td=inp.closest('tr').querySelector('td:first-child');
  const ref=getBomRefs(_renderingSupName,inp.value);
  td.textContent=ref; td.title=ref; td.style.color=ref==='-'?'#ccc':'#555';
}}
function sortSmat(field) {{
  const rows=[];
  document.querySelectorAll('#smat tr').forEach(tr=>{{
    const ins=tr.querySelectorAll('input'); if(ins.length<8) return;
    const bomRef=tr.querySelector('td:first-child')?.textContent?.trim()||'-';
    rows.push({{_bomRef:bomRef,name:ins[0].value,spec:ins[1].value,unit:ins[2].value,
      unit_price:parseFloat(ins[3].value)||0,moq:parseFloat(ins[4].value)||1,
      option:ins[5].value,purchase_source:ins[6].value,note:ins[7].value}});
  }});
  if(_supSortCol===field) _supSortDir*=-1; else {{_supSortCol=field;_supSortDir=1;}}
  rows.sort((a,b)=>{{
    const va=typeof a[field]==='number'?a[field]:(a[field]||'').toLowerCase();
    const vb=typeof b[field]==='number'?b[field]:(b[field]||'').toLowerCase();
    return va<vb?-_supSortDir:va>vb?_supSortDir:0;
  }});
  document.getElementById('smat').innerHTML='';
  rows.forEach(m=>addSMatRow(m));
  document.querySelectorAll('[id^="ssi-"]').forEach(el=>el.textContent='');
  const si=document.getElementById('ssi-'+field); if(si) si.textContent=_supSortDir===1?' ▲':' ▼';
}}
async function saveSup(idx) {{
  const nm=document.getElementById('s-nm').value.trim();
  if(!nm) {{ alert('업체명을 입력하세요.'); return; }}
  const mats=[];
  document.querySelectorAll('#smat tr').forEach(tr=>{{
    const ins=tr.querySelectorAll('input'); if(ins.length<8) return;
    mats.push({{name:ins[0].value,spec:ins[1].value,unit:ins[2].value,
      unit_price:parseFloat(ins[3].value)||0,moq:parseFloat(ins[4].value)||1,
      option:ins[5].value,purchase_source:ins[6].value,note:ins[7].value}});
  }});
  const sup={{name:nm,contact:document.getElementById('s-ct').value,email:document.getElementById('s-em').value,
    address:document.getElementById('s-ad').value,note:document.getElementById('s-nt').value,materials:mats}};
  if(idx<0) {{ supData.suppliers.push(sup); selSup=supData.suppliers.length-1; }}
  else supData.suppliers[idx]=sup;
  supData.updated_at=new Date().toISOString().slice(0,10);
  const sst=document.getElementById('sup-st'); sst.textContent='저장 중...';
  try {{
    await ghPut('suppliers.json',supData,'업체 업데이트: '+nm);
    sst.textContent='저장 완료';
    renderSupList();
  }} catch(e) {{ sst.textContent=''; alert('저장 실패: '+e.message); }}
}}
async function delSup(idx) {{
  if(!confirm(`'${{supData.suppliers[idx].name}}' 업체를 삭제하시겠습니까?`)) return;
  supData.suppliers.splice(idx,1); selSup=null;
  supData.updated_at=new Date().toISOString().slice(0,10);
  try {{
    await ghPut('suppliers.json',supData,'업체 삭제');
    renderSupList();
    document.getElementById('sup-detail').innerHTML='<div class="detail-empty">업체를 선택하거나 추가하세요</div>';
  }} catch(e) {{ alert('삭제 실패: '+e.message); }}
}}

// ── Schedule ─────────────────────────────────
let schData=null, calYear=0, calMonth=0, selDate='';
const DOW=['일','월','화','수','목','금','토'];

async function initSchedule() {{
  const {{data}}=await ghGet('schedule.json');
  schData=data||{{events:[]}};
  const now=new Date();
  calYear=now.getFullYear(); calMonth=now.getMonth();
  renderCalendar();
}}

function calMove(dir) {{
  calMonth+=dir;
  if(calMonth<0){{calMonth=11;calYear--;}}
  if(calMonth>11){{calMonth=0;calYear++;}}
  renderCalendar();
}}

function renderCalendar() {{
  document.getElementById('cal-title').textContent=`${{calYear}}년 ${{calMonth+1}}월`;
  const evtDates={{}};
  (schData&&schData.events||[]).forEach(e=>{{
    if(!evtDates[e.date]) evtDates[e.date]=[];
    evtDates[e.date].push(e.type||'기타');
  }});
  const todayStr=new Date().toISOString().slice(0,10);
  const first=new Date(calYear,calMonth,1).getDay();
  const last=new Date(calYear,calMonth+1,0).getDate();
  const prevLast=new Date(calYear,calMonth,0).getDate();
  let html=DOW.map(d=>`<div class="cal-dh">${{d}}</div>`).join('');
  for(let i=first-1;i>=0;i--)
    html+=`<div class="cal-day other-m"><div class="cal-dn">${{prevLast-i}}</div></div>`;
  for(let d=1;d<=last;d++) {{
    const ds=`${{calYear}}-${{String(calMonth+1).padStart(2,'0')}}-${{String(d).padStart(2,'0')}}`;
    const dow=new Date(calYear,calMonth,d).getDay();
    const cls=['cal-day'];
    if(ds===todayStr) cls.push('today');
    if(ds===selDate) cls.push('selected');
    if(dow===0) cls.push('sun'); if(dow===6) cls.push('sat');
    const dots=(evtDates[ds]||[]).slice(0,5).map(t=>`<div class="cal-dot ${{t}}"></div>`).join('');
    html+=`<div class="${{cls.join(' ')}}" onclick="selectDate('${{ds}}')"><div class="cal-dn">${{d}}</div><div class="cal-dots">${{dots}}</div></div>`;
  }}
  const rem=(7-(first+last)%7)%7;
  for(let d=1;d<=rem;d++) html+=`<div class="cal-day other-m"><div class="cal-dn">${{d}}</div></div>`;
  document.getElementById('cal-grid').innerHTML=html;
}}

function selectDate(ds) {{
  selDate=ds;
  renderCalendar();
  const dt=new Date(ds+'T00:00:00');
  document.getElementById('evt-date-title').textContent=`${{dt.getMonth()+1}}월 ${{dt.getDate()}}일 (${{DOW[dt.getDay()]}}) 일정`;
  document.getElementById('add-evt-btn').style.display='';
  renderEvtList();
}}

function renderEvtList() {{
  const evts=(schData&&schData.events||[]).filter(e=>e.date===selDate)
    .sort((a,b)=>(a.time||'').localeCompare(b.time||''));
  const el=document.getElementById('evt-list');
  if(!evts.length){{
    el.innerHTML='<div style="color:#ccc;font-size:13px;text-align:center;padding:28px 0">이 날짜에 등록된 일정이 없어요</div>';
    return;
  }}
  el.innerHTML=evts.map(e=>`
    <div class="evt-card">
      <span class="evt-badge ${{e.type||'기타'}}">${{e.type||'기타'}}</span>
      <div class="evt-body">
        <div class="evt-title">${{e.title||''}}</div>
        <div class="evt-meta">${{[e.time,e.location].filter(Boolean).join(' · ')}}</div>
        ${{e.detail?`<div class="evt-detail">${{e.detail}}</div>`:''}}
      </div>
      <button class="evt-del" onclick="deleteSchEvent(${{e.id}})">×</button>
    </div>`).join('');
}}

function openSchModal() {{
  document.getElementById('sch-date').value=selDate;
  document.getElementById('sch-title').value='';
  document.getElementById('sch-time').value='';
  document.getElementById('sch-loc').value='';
  document.getElementById('sch-detail').value='';
  document.getElementById('sch-type').value='판매행사';
  document.getElementById('sch-st').textContent='';
  document.getElementById('sch-modal').style.display='flex';
}}
function closeSchModal(){{ document.getElementById('sch-modal').style.display='none'; }}

async function saveSchEvent() {{
  const title=document.getElementById('sch-title').value.trim();
  const date=document.getElementById('sch-date').value;
  if(!title||!date){{alert('제목과 날짜는 필수입니다.');return;}}
  const evt={{id:Date.now(),date,title,
    time:document.getElementById('sch-time').value,
    location:document.getElementById('sch-loc').value.trim(),
    type:document.getElementById('sch-type').value,
    detail:document.getElementById('sch-detail').value.trim()}};
  schData.events.push(evt);
  const st=document.getElementById('sch-st'); st.textContent='저장 중...';
  try {{
    await ghPut('schedule.json',schData,'일정 추가: '+title);
    st.textContent='저장 완료';
    setTimeout(closeSchModal,600);
    if(selDate===date) renderEvtList();
    renderCalendar();
  }} catch(e) {{ st.textContent=''; schData.events.pop(); alert('저장 실패: '+e.message); }}
}}

async function deleteSchEvent(id) {{
  if(!confirm('이 일정을 삭제할까요?')) return;
  const idx=schData.events.findIndex(e=>e.id===id);
  if(idx<0) return;
  const removed=schData.events.splice(idx,1)[0];
  try {{
    await ghPut('schedule.json',schData,'일정 삭제');
    renderEvtList(); renderCalendar();
  }} catch(e) {{ schData.events.splice(idx,0,removed); alert('삭제 실패: '+e.message); }}
}}

// ── Charts ───────────────────────────────────
const _dayL={chart_labels}, _dayD={chart_data};
const _weekL={weekly_labels}, _weekD={weekly_data};
const _monthL={monthly_labels}, _monthD={monthly_data};
const MONTH_QTY={month_qty_json};
let salesChartInst=null;

function switchSalesChart(mode,btn) {{
  document.querySelectorAll('.chart-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const L=mode==='day'?_dayL:mode==='week'?_weekL:_monthL;
  const D=mode==='day'?_dayD:mode==='week'?_weekD:_monthD;
  salesChartInst.data.labels=L;
  salesChartInst.data.datasets[0].data=D;
  salesChartInst.update();
}}

function updateProfitKpi() {{
  if(!costData) return;
  let total=0;
  PRODS.forEach(prod=>{{
    const c=costData.products[prod]; if(!c||!c.consumer_price) return;
    const cp=c.consumer_price, p7=Math.round(cp*0.93);
    const bomT=(c.materials||[]).reduce((s,m)=>s+Math.round((m.qty||0)*(m.unit_price||0)),0);
    const itemT=(c.items||[]).reduce((s,it)=>s+Math.round((it.qty||0)*(it.unit_price||0)),0);
    const fee7=Math.round(p7*0.019);
    const pf7=p7-(bomT+itemT)-(c.shipping||0)-fee7;
    total+=pf7*(MONTH_QTY[prod]||0);
  }});
  const el=document.getElementById('profit-kpi');
  if(el){{el.textContent=total.toLocaleString()+'원';el.style.color=total>=0?'#111':'#e53535';}}
}}

function initCharts() {{
  const yTick={{ticks:{{callback:v=>v.toLocaleString()+'원'}}}};
  salesChartInst=new Chart(document.getElementById('salesChart'),{{
    type:'bar',
    data:{{labels:_dayL,datasets:[{{label:'매출',data:_dayD,
      backgroundColor:'rgba(17,17,17,0.1)',borderColor:'#111',borderWidth:1.5,borderRadius:3}}]}},
    options:{{plugins:{{legend:{{display:false}}}},scales:{{y:yTick}}}}
  }});
  new Chart(document.getElementById('statusChart'),{{
    type:'doughnut',
    data:{{labels:{status_labels},datasets:[{{data:{status_vals},
      backgroundColor:['#111','#444','#777','#aaa','#ccc','#eee']}}]}},
    options:{{plugins:{{legend:{{position:'bottom',labels:{{font:{{size:10}}}}}}}}}}
  }});
  const PALETTE=['#111','#444','#777','#999','#bbb','#ddd'];
  new Chart(document.getElementById('prodRevenueChart'),{{
    type:'doughnut',
    data:{{labels:{rev_labels},datasets:[{{data:{rev_data},backgroundColor:PALETTE}}]}},
    options:{{plugins:{{legend:{{position:'bottom',labels:{{font:{{size:10}}}}}}}}}}
  }});
  new Chart(document.getElementById('prodSalesChart'),{{
    type:'bar',
    data:{{labels:{best_labels},datasets:[{{label:'판매량',data:{best_vals},
      backgroundColor:'rgba(17,17,17,0.15)',borderColor:'#111',borderWidth:1.5,borderRadius:3}}]}},
    options:{{indexAxis:'y',plugins:{{legend:{{display:false}}}},
      scales:{{x:{{ticks:{{callback:v=>v+'개'}}}}}}}}
  }});
}}
</script>
</body>
</html>"""

with open("dashboard.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"dashboard.html 생성 완료!")
print(f"기본 로그인: admin / papier2024")
print(f"  이번달 매출: {int(total_month):,}원 / 주문 {order_count}건")

if not os.environ.get("CI"):
    import webbrowser
    webbrowser.open("file://" + os.path.abspath("dashboard.html"))
