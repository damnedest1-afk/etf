# -*- coding: utf-8 -*-
import os, json, time, datetime as dt, urllib.request
from pykrx import stock

KST = dt.timezone(dt.timedelta(hours=9))
def ymd(d): return d.strftime("%Y%m%d")

def recent_bday():
    d = dt.datetime.now(KST).date()
    for i in range(0, 8):
        day = ymd(d - dt.timedelta(days=i))
        try:
            df = stock.get_etf_ohlcv_by_ticker(day)
            if df is not None and len(df) > 50:
                return day, df
        except Exception as e:
            print("  ohlcv try", day, "fail:", e)
        time.sleep(0.5)
    raise RuntimeError("최근 거래일 데이터를 찾지 못함")

def close_map(day):
    try:
        df = stock.get_etf_ohlcv_by_ticker(day)
        return {t: float(df.loc[t, "종가"]) for t in df.index}
    except Exception as e:
        print("  close_map", day, "fail:", e); return {}

def find_close_map(target_date):
    for i in range(0, 6):
        m = close_map(ymd(target_date - dt.timedelta(days=i)))
        if m: return m
    return {}

def collect_krx():
    day, base = recent_bday()
    today = dt.datetime.strptime(day, "%Y%m%d").date()
    print("기준 거래일:", day, "종목수:", len(base))
    print("KRX 컬럼:", list(base.columns))
    now_close = {t: float(base.loc[t, "종가"]) for t in base.index}
    maps = {}
    for key, days in {"r1":30, "r3":91, "r6":182, "r12":365}.items():
        maps[key] = find_close_map(today - dt.timedelta(days=days)); time.sleep(0.3)
    names = {}
    try:
        for t in stock.get_etf_ticker_list(day):
            try: names[t] = stock.get_etf_ticker_name(t)
            except Exception: pass
    except Exception as e:
        print("name fail:", e)
    def col(t, *cands):
        for c in cands:
            if c in base.columns:
                try: return float(base.loc[t, c])
                except Exception: pass
        return 0.0
    rows = []
    for t in base.index:
        nowc = now_close.get(t, 0.0)
        def ret(key):
            b = maps[key].get(t)
            return round((nowc/b - 1)*100, 2) if (b and nowc) else None
        nav_tot = col(t, "순자산총액", "시가총액")
        rows.append({
            "code": t, "name": names.get(t, ""),
            "aum": round(nav_tot/1e8) if nav_tot else 0,
            "turn": round(col(t, "거래대금")/1e8),
            "r1": ret("r1"), "r3": ret("r3"), "r6": ret("r6"), "r12": ret("r12"),
            "nav": nowc, "updated": day,
        })
    return rows, day

def upsert_supabase(rows):
    url = os.environ.get("SUPABASE_URL"); key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("Supabase 시크릿 없음"); return
    endpoint = url.rstrip("/") + "/rest/v1/etfs"
    headers = {"apikey": key, "Authorization": "Bearer "+key,
               "Content-Type": "application/json",
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    for i in range(0, len(rows), 500):
        chunk = rows[i:i+500]
        data = json.dumps(chunk, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print("  업서트", i, "~", i+len(chunk), ":", r.status)
        except Exception as e:
            print("  업서트 실패:", e); raise

def main():
    rows, day = collect_krx()
    print("수집 완료:", len(rows), "종목")
    upsert_supabase(rows)
    print("끝!")

if __name__ == "__main__":
    main()
