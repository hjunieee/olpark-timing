"""실시간 주차 대수(동2문·남2문·북2문)와 기관 예상 이용률을 받아 site/data/now.json에 쓴다.

출처: 한국체육산업개발(주) 실시간 주차현황(공공데이터포털 15168686)이 안내하는
올림픽공원 '주차장 예상 이용률 안내' 공개 페이지. 로그인·인증키가 필요 없다.
GitHub Actions가 30분마다 실행한다. 직전 값은 배포된 now.json에서 읽어 최근 7일치를 이어 붙인다.
"""
import datetime as dt, html, json, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'site' / 'data' / 'now.json'
SRC = 'https://www.ksponco.or.kr/online/main/parking.do'
PREV = 'https://hjunieee.github.io/olpark-timing/data/now.json'
UA = {'User-Agent': 'Mozilla/5.0 (olpark-timing realtime)'}


def kst_now():
    return dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(hours=9)


def parse(page: str):
    m = re.search(r'실시간 주차대수[^:]*:\s*<strong[^>]*>\s*([\d,]+)\s*대\s*</strong>\s*주차 중\s*/\s*([\d,]+)\s*대', page)
    if not m:
        raise ValueError('실시간 주차대수 문구를 찾지 못했다')
    parked, cap = int(m.group(1).replace(',', '')), int(m.group(2).replace(',', ''))
    pred = []
    for d, hm, r in re.findall(r'<th>\s*(\d{4}-\d{2}-\d{2})(?:&nbsp;|\s)+(\d{2}:\d{2}):\d{2}\s*</th>.*?<td[^>]*>\s*(\d+)%\s*</td>', page, re.S):
        pred.append({'t': f'{d} {hm}', 'rate': int(r)})
    return parked, cap, pred


def main():
    now = kst_now().strftime('%Y-%m-%d %H:%M')
    log = []
    try:
        old = json.loads(urllib.request.urlopen(urllib.request.Request(PREV, headers=UA), timeout=20).read())
        log = old.get('log', [])
    except Exception as e:
        print('이전 기록 없음', e)
    try:
        page = urllib.request.urlopen(urllib.request.Request(SRC, headers=UA), timeout=30).read().decode('utf-8', 'replace')
        parked, cap, pred = parse(page)
    except Exception as e:
        print('실시간 받기 실패', e)
        if log:   # 직전 값을 그대로 두되 실패를 표시한다
            OUT.write_text(json.dumps({**old, 'error': f'{now} 갱신 실패'}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        return 0
    cutoff = (kst_now() - dt.timedelta(days=7)).strftime('%Y-%m-%d %H:%M')
    log = [x for x in log if x['t'] >= cutoff and x['t'] != now] + [{'t': now, 'n': parked}]
    OUT.write_text(json.dumps({'stamp': now, 'parked': parked, 'capacity': cap, 'agencyPred': pred, 'log': log,
                               'source': '한국체육산업개발(주) 실시간 주차현황(동2문·남2문·북2문)'}, ensure_ascii=False, separators=(',', ':')),
                   encoding='utf-8')
    print('실시간', now, parked, '/', cap, '예상 이용률', len(pred), '건')
    return 0


if __name__ == '__main__':
    sys.exit(main())
