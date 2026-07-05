# -*- coding: utf-8 -*-
import os, json, time, datetime as dt, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Referer": "https://finance.naver.com/sise/etf.naver"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("euc-kr", "replace")

def collect():
    url = ("https://finance.naver.com/api/sise/etfItemList.nhn"
           "?etfType=0&targetColumn=market_sum&sortOrder=desc")
    data = json.loads(get(url))
    items = data["result"]["etfItemList"]
    print("네이버 목록 수신:", len(items), "종목")
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d")
    rows = []
    for it in items:
        code = str(it.get("itemcode", "")).strip()
        name = str(it.get("itemname", "")).strip()
        if not code or not name:
            continue
        r3 = it.get("threeMonthEarnRate")
        rows.append({
            "code": code, "name": name,
            "aum": int(it.get("marketSum") or 0),
            "turn": round((it.get("amonut") or 0) / 100),
            "r3": round(float(r3), 2) if r3 not in (None, "") else None,
            "r1": None, "r6": None, "r12": None,
            "nav": float(it.get("nowVal") or 0),
            "updated": today,
        })
    return rows

def enrich_returns(rows, limit=300):
    end = dt.datetime.now().strftime("%Y%m%d")
    start = (dt.datetime.now() - dt.timedelta(days=420)).strftime("%Y%m%d")
    n = 0
    for row in rows:
        if limit and n >= limit:
            break
        code = row["code"]
        try:
            u = (f"https://fchart.stock.naver.com/siseJson.naver?symbol={code}"
                 f"&requestType=1&startTime={start}&endTime={end}&timeframe=day")
            arr = json.loads(get(u).replace("'", '"'))
            pts = [(str(x[0]), float(x[4])) for x in arr[1:] if str(x[0]).isdigit()]
            if len(pts) < 25:
                continue
            last = pts[-1][1]
            def ret(days):
                cut = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y%m%d")
                base = None
                for d, c in pts:
                    if d <= cut: base = c
                    else: break
                if base is None: base = pts[0][1]
                return round((last/base - 1)*100, 2) if base else None
            row["r1"], row["r3"], row["r6"], row["r12"] = ret(30), ret(91), ret(182), ret(365)
            n += 1
            time.sleep(0.05)
        except Exception:
            continue
    print("수익률 상세 계산:", n, "종목")

def upsert(rows):
    url = os.environ.get("SUPABASE_URL"); key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("Supabase 시크릿 없음 → 저장 생략"); return
    ep = url.rstrip("/") + "/rest/v1/etfs"
    hd = {"apikey": key, "Authorization": "Bearer " + key,
          "Content-Type": "application/json",
          "Prefer": "resolution=merge-duplicates,return=minimal"}
    for i in range(0, len(rows), 500):
        chunk = rows[i:i+500]
        body = json.dumps(chunk, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(ep, data=body, headers=hd, method="POST")
        with urllib.request.urlopen(req, timeout=40) as r:
            print("  업서트", i, "~", i+len(chunk), ":", r.status)

def main():
    rows = collect()
    enrich_returns(rows, limit=300)
    upsert(rows)
    print("끝! 총", len(rows), "종목")

if __name__ == "__main__":
    main()
