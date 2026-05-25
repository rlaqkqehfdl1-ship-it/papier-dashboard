"""GitHub Actions 전용 래퍼 — 토큰 갱신 후 대시보드 생성"""
import requests, json, base64, os, subprocess, sys, shutil
from datetime import datetime

CLIENT_ID     = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]
GH_PAT        = os.environ.get("GH_PAT", "")
GH_REPO       = os.environ.get("GH_REPO", "")
MALL_ID       = "papierarchive"

# ── 1. 액세스 토큰 갱신 ──────────────────────
print("토큰 갱신 중...")
cred = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
r = requests.post(
    f"https://{MALL_ID}.cafe24api.com/api/v2/oauth/token",
    headers={"Authorization": f"Basic {cred}", "Content-Type": "application/x-www-form-urlencoded"},
    data={"grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN}
)
tokens = r.json()

if "access_token" not in tokens:
    print(f"토큰 갱신 실패: {tokens}")
    sys.exit(1)

print(f"토큰 갱신 완료 (만료: {tokens['expires_at']})")
with open("tokens.json", "w") as f:
    json.dump(tokens, f, indent=2)

# ── 2. 다음 실행을 위해 새 refresh_token을 GitHub Secret에 저장 ──
if GH_PAT and GH_REPO and "refresh_token" in tokens:
    try:
        from nacl import encoding, public
        owner, repo = GH_REPO.split("/", 1)

        key_r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key",
            headers={"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"}
        )
        key_data = key_r.json()

        pk = public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder())
        encrypted = base64.b64encode(
            public.SealedBox(pk).encrypt(tokens["refresh_token"].encode())
        ).decode()

        resp = requests.put(
            f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/REFRESH_TOKEN",
            headers={"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"},
            json={"encrypted_value": encrypted, "key_id": key_data["key_id"]}
        )
        print(f"REFRESH_TOKEN 시크릿 업데이트 완료 (HTTP {resp.status_code})")
    except Exception as e:
        print(f"시크릿 업데이트 실패 (무시): {e}")

# ── 3. stock.json 초기화 (최초 실행 시에만) ──
if GH_PAT and GH_REPO:
    owner, repo = GH_REPO.split("/", 1)
    gh_headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"}
    api_headers = {"Authorization": f"Bearer {tokens['access_token']}", "X-Cafe24-Api-Version": "2026-03-01"}
    stock_check = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/contents/stock.json", headers=gh_headers)
    if stock_check.status_code == 404:
        print("stock.json 없음 — Cafe24 데이터로 초기화...")
        products = requests.get(
            f"https://papierarchive.cafe24api.com/api/v2/admin/products",
            headers=api_headers, params={"limit": 100}
        ).json().get("products", [])
        stock_products = []
        for p in [x for x in products if float(x.get("price", "0")) > 0]:
            variants = requests.get(
                f"https://papierarchive.cafe24api.com/api/v2/admin/products/{p['product_no']}/variants",
                headers=api_headers
            ).json().get("variants", [])
            svariants = []
            for v in variants:
                opt = " / ".join(o["value"] for o in (v.get("options") or [])
                                 if o.get("value") and o["value"] != "N") or "단품"
                svariants.append({"option": opt, "qty": int(v.get("stock_quantity") or 0)})
            if svariants:
                stock_products.append({"product_name": p["product_name"], "variants": svariants})
        stock_data = {"updated_at": datetime.now().strftime("%Y-%m-%d"), "products": stock_products}
        content = base64.b64encode(
            json.dumps(stock_data, indent=2, ensure_ascii=False).encode()).decode()
        r2 = requests.put(
            f"https://api.github.com/repos/{owner}/{repo}/contents/stock.json",
            headers=gh_headers,
            json={"message": "초기 재고 데이터 생성 (Cafe24 동기화)", "content": content}
        )
        print(f"stock.json 생성 완료 (HTTP {r2.status_code})")
    else:
        print("stock.json 존재 — 유지")

# ── 4. 대시보드 HTML 생성 ────────────────────
print("대시보드 생성 중...")
result = subprocess.run([sys.executable, "dashboard.py"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
    sys.exit(result.returncode)

# ── 5. GitHub Pages 배포용 폴더 준비 ─────────
os.makedirs("public", exist_ok=True)
shutil.copy("dashboard.html", "public/index.html")
print("배포 준비 완료: public/index.html")
