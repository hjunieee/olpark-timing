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


if __name__ == '__main__':
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    if cmd == 'probe': probe()
    else:
        for i in (sys.argv[2:] or APIS):
            fetch_all(i)
