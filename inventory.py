"""
papier archive 재고 관리 CLI
실행: python inventory.py
"""
import requests, json, base64, sys, os
from datetime import datetime, timedelta

CLIENT_ID     = "J2dzflmWekLd28v00yHuUK"
CLIENT_SECRET = "eb6beJ7TAkbTemPZfEA5mi"
MALL_ID       = "papierarchive"
TOKEN_FILE    = "tokens.json"
BASE          = f"https://{MALL_ID}.cafe24api.com/api/v2/admin"
API_VER       = "2026-03-01"
GH_TOKEN      = os.environ.get("GH_PAT", "")           # 환경변수 또는 빈값
GH_REPO       = "rlaqkqehfdl1-ship-it/papier-dashboard"

# ── 토큰 관리 ─────────────────────────────────
def refresh_token(refresh_tok):
    cred = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        f"https://{MALL_ID}.cafe24api.com/api/v2/oauth/token",
        headers={"Authorization": f"Basic {cred}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": refresh_tok}
    )
    return r.json()

def reauth():
    """재인증: 브라우저에서 코드 발급 후 토큰 교환"""
    print("\n[재인증 필요]")
    print("아래 URL을 브라우저에서 열고 동의 후 code= 값을 복사하세요:")
    print(f"https://{MALL_ID}.cafe24api.com/api/v2/oauth/authorize"
          f"?response_type=code&client_id={CLIENT_ID}"
          f"&redirect_uri=https%3A%2F%2Fpapierarchive.cafe24.com"
          f"&scope=mall.read_application,mall.read_category,mall.read_product,"
          f"mall.write_product,mall.read_order,mall.read_salesreport")
    code = input("\ncode= 값 붙여넣기: ").strip()
    cred = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        f"https://{MALL_ID}.cafe24api.com/api/v2/oauth/token",
        headers={"Authorization": f"Basic {cred}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "authorization_code", "code": code,
              "redirect_uri": "https://papierarchive.cafe24.com"}
    )
    return r.json()

def update_gh_secret(new_refresh_token):
    """GitHub Secret의 REFRESH_TOKEN을 최신 값으로 업데이트"""
    try:
        from nacl import encoding, public
        owner, repo = GH_REPO.split("/", 1)
        gh_headers = {"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        key_data = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key",
            headers=gh_headers).json()
        pk = public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder())
        encrypted = base64.b64encode(public.SealedBox(pk).encrypt(new_refresh_token.encode())).decode()
        requests.put(
            f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/REFRESH_TOKEN",
            headers=gh_headers,
            json={"encrypted_value": encrypted, "key_id": key_data["key_id"]}
        )
    except Exception:
        pass  # 시크릿 업데이트 실패해도 로컬 실행에는 영향 없음

def get_access_token():
    """유효한 액세스 토큰 반환 (자동 갱신 / 재인증 포함)"""
    tokens = {}
    if os.path.exists(TOKEN_FILE):
        tokens = json.load(open(TOKEN_FILE))

    # 현재 토큰이 유효한지 테스트
    if tokens.get("access_token"):
        r = requests.get(f"{BASE}/products?limit=1",
                         headers={"Authorization": f"Bearer {tokens['access_token']}",
                                  "X-Cafe24-Api-Version": API_VER})
        if r.status_code == 200:
            return tokens["access_token"]

    # refresh 시도
    if tokens.get("refresh_token"):
        new = refresh_token(tokens["refresh_token"])
        if "access_token" in new:
            json.dump(new, open(TOKEN_FILE, "w"), indent=2)
            update_gh_secret(new["refresh_token"])
            return new["access_token"]

    # 재인증
    new = reauth()
    if "access_token" not in new:
        print(f"인증 실패: {new}")
        sys.exit(1)
    json.dump(new, open(TOKEN_FILE, "w"), indent=2)
    update_gh_secret(new["refresh_token"])
    return new["access_token"]

def H():
    return {"Authorization": f"Bearer {get_access_token()}", "X-Cafe24-Api-Version": API_VER}

# ── API 헬퍼 ──────────────────────────────────
def api_get(path, **params):
    return requests.get(f"{BASE}{path}", headers=H(), params=params).json()

def api_put(path, body):
    return requests.put(f"{BASE}{path}", headers={**H(), "Content-Type": "application/json"},
                        data=json.dumps(body)).json()

# ── 기능 ──────────────────────────────────────
def list_inventory():
    """전체 상품 + 옵션별 재고 조회"""
    products = api_get("/products", limit=100).get("products", [])
    real = [p for p in products if float(p.get("price", "0")) > 0]

    print(f"\n{'='*60}")
    print(f"  재고 현황  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print(f"{'='*60}")

    inventory = []
    for p in real:
        variants = api_get(f"/products/{p['product_no']}/variants").get("variants", [])
        for v in variants:
            opt = " / ".join(o["value"] for o in v.get("options", [])
                             if o.get("value") and o["value"] != "N") or "단품"
            qty = int(v.get("stock_quantity") or 0)
            inventory.append({
                "product_name": p["product_name"],
                "product_no":   p["product_no"],
                "variant_code": v["variant_code"],
                "option":       opt,
                "qty":          qty,
            })

    for idx, v in enumerate(inventory, 1):
        status = "품절" if v["qty"] == 0 else ("⚠부족" if v["qty"] <= 5 else "정상")
        print(f"  {idx:2}. {v['product_name']} [{v['option']}]  {v['qty']}개  [{status}]")

    print(f"{'='*60}")
    return inventory

def update_stock(inventory):
    """재고 수량 수정"""
    try:
        num = int(input("\n수정할 항목 번호 (0=취소): ").strip())
    except ValueError:
        return
    if num == 0 or num > len(inventory):
        return

    item = inventory[num - 1]
    print(f"\n선택: {item['product_name']} [{item['option']}]  현재 {item['qty']}개")
    try:
        new_qty = int(input("새로운 재고 수량: ").strip())
    except ValueError:
        print("숫자를 입력하세요.")
        return

    result = api_put(
        f"/products/{item['product_no']}/variants/{item['variant_code']}",
        {"shop_no": "1", "variants": [{"stock_quantity": str(new_qty)}]}
    )

    if result.get("variant") or result.get("variants"):
        print(f"  업데이트 완료: {item['qty']}개 → {new_qty}개")
    else:
        print(f"  실패: {result}")

# ── 메인 루프 ─────────────────────────────────
def main():
    print("\npapier archive 재고 관리")
    while True:
        print("\n[메뉴]  1. 재고 조회  2. 재고 수정  0. 종료")
        choice = input("> ").strip()
        if choice == "0":
            break
        elif choice == "1":
            list_inventory()
        elif choice == "2":
            inventory = list_inventory()
            update_stock(inventory)
        else:
            print("1, 2, 0 중에 선택하세요.")

if __name__ == "__main__":
    main()
