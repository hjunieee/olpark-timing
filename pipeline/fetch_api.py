"""문화데이터광장(api.kcisa.kr) API 수집. 키는 환경변수 CULTURE_KEY(또는 CULTURE_KEY_675 등)로만 읽는다.

사용: python pipeline/fetch_api.py probe   → 각 API 1쪽만 받아 cache/probe_*.txt에 저장(형식 확인용)
      python pipeline/fetch_api.py all     → 전체 쪽을 cache/api_<id>/에 저장
키 값은 출력하지 않는다. 오류 메시지에서도 키를 지운다.
"""
import os, sys, json, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'cache'; CACHE.mkdir(exist_ok=True)
APIS = {
    '675': 'https://api.kcisa.kr/openapi/API_CPM_009/request',   # 2025 입출차·공연·날씨 연계
    '659': 'https://api.kcisa.kr/openapi/API_CPM_008/request',   # 2025 입출차정보
    '96': 'https://api.kcisa.kr/openapi/service/rest/meta/KSCperf',  # 공연행사정보
}


def load_env():
    f = ROOT.parent / '.env'
    if f.exists():
        for line in f.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1); os.environ.setdefault(k.strip(), v.strip())


def key_for(api_id):
    return os.environ.get(f'CULTURE_KEY_{api_id}') or os.environ.get('CULTURE_KEY')


def get(api_id, page, rows, as_json=True):
    key = key_for(api_id)
    if not key: raise SystemExit(f'키 없음: CULTURE_KEY 또는 CULTURE_KEY_{api_id}')
    q = urllib.parse.urlencode({'serviceKey': key, 'numOfRows': rows, 'pageNo': page})
    req = urllib.request.Request(f'{APIS[api_id]}?{q}', headers={'Accept': 'application/json' if as_json else 'application/xml',
                                                                 'User-Agent': 'olpark-timing'})
    try:
        return urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace')
    except Exception as e:
        raise RuntimeError(str(e).replace(key, '***'))


def probe():
    for i in APIS:
        try:
            txt = get(i, 1, 5)
        except Exception as e:
            txt = f'ERROR {e}'
        (CACHE / f'probe_{i}.txt').write_text(txt, encoding='utf-8')
        print(i, len(txt), txt[:300].replace('\n', ' '))


def fetch_all(api_id, rows=1000, max_pages=5000):
    d = CACHE / f'api_{api_id}'; d.mkdir(exist_ok=True)
    for p in range(1, max_pages + 1):
        f = d / f'{p:05d}.json'
        if f.exists() and f.stat().st_size > 200:
            continue
        txt = get(api_id, p, rows)
        f.write_text(txt, encoding='utf-8')
        if '"item"' not in txt and '<item>' not in txt:
            print(api_id, '마지막 쪽', p); f.unlink(); break
        if p % 20 == 0: print(api_id, p, '쪽')
        time.sleep(0.2)


DESC_RE = None


def parse_659(txt):
    """659 응답 한 쪽 → (입구, 입차, 출구, 출차) 행 목록."""
    import re
    global DESC_RE
    DESC_RE = DESC_RE or re.compile(r'입구:([^,]*), 입차시간:([^,]*), 출구:([^,]*), 출차시간:(.*)$')
    items = json.loads(txt)['response']['body']['items']
    items = items.get('item', []) if isinstance(items, dict) else []
    if isinstance(items, dict): items = [items]
    out = []
    for it in items:
        m = DESC_RE.match((it.get('DESCRIPTION') or '').strip())
        if m: out.append([x.strip() for x in m.groups()])
    return out


def fetch_659(rows=5000):
    """2025 입출차 전체를 cache/api_659/NNNNN.csv로 받는다. 429면 쉬었다 다시 한다."""
    import csv
    d = CACHE / 'api_659'; d.mkdir(exist_ok=True)
    total = None
    for wait in (5, 30, 60, 120, 300):
        try: total = int(json.loads(get('659', 1, 1))['response']['body']['totalCount']); break
        except Exception as e: print('재시도 0', str(e)[:80], flush=True); time.sleep(wait)
    if total is None: raise SystemExit('전체 건수 조회 실패')
    time.sleep(2)
    pages = (total + rows - 1) // rows
    print('659 전체', total, '건,', pages, '쪽', flush=True)
    for p in range(1, pages + 1):
        f = d / f'{p:05d}.csv'
        if f.exists(): continue
        for wait in (2, 5, 15, 30, 60, 120, 300):
            try:
                recs = parse_659(get('659', p, rows)); break
            except Exception as e:
                print('재시도', p, str(e)[:80], flush=True); time.sleep(wait)
        else:
            raise SystemExit(f'{p}쪽 실패')
        with open(f, 'w', newline='', encoding='utf-8') as fh:
            csv.writer(fh).writerows(recs)
        if p % 25 == 0: print(p, '/', pages, flush=True)
        time.sleep(2.0)
    print('DONE_659', flush=True)


def load_io_2025():
    """cache/api_659/*.csv → in/out 시각 DataFrame (2025년, 중복 제거)."""
    import pandas as pd
    fs = sorted((CACHE / 'api_659').glob('*.csv'))
    df = pd.concat([pd.read_csv(f, header=None, names=['gin', 'in', 'gout', 'out'], dtype=str) for f in fs], ignore_index=True)
    df = df.drop_duplicates()
    io = pd.DataFrame({'in': pd.to_datetime(df['in'], errors='coerce'), 'out': pd.to_datetime(df['out'], errors='coerce'),
                       'gin': df['gin'], 'gout': df['gout']})
    return io.dropna(subset=['in'])


if __name__ == '__main__':
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    if cmd == 'probe': probe()
    elif cmd == '659': fetch_659()
    else:
        for i in (sys.argv[2:] or APIS):
            fetch_all(i)
