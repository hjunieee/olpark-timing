"""올팍타이밍 공통 함수: 경로, 공휴일, 공연 시각 파싱, 특징 만들기."""
import json, re
from pathlib import Path
import numpy as np
import pandas as pd
import holidays

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'cache'          # 원자료 캐시 (git 제외 가능)
SITE_DATA = ROOT / 'site' / 'data'
CACHE.mkdir(exist_ok=True); SITE_DATA.mkdir(parents=True, exist_ok=True)

KR_HOL = holidays.KR(years=range(2023, 2029))

# 공연장 규모 가중치(대략적 수용 인원, 천 명 단위). 공식 좌석 수 기준 근사.
VENUES = [
    ('KSPO DOME', 15.0, True),
    ('핸드볼', 5.0, True), ('라이브 아레나', 5.0, True), ('티켓링크', 5.0, True),
    ('올림픽홀', 3.0, False),
    ('우리금융아트홀', 1.2, False), ('K-아트홀', 1.0, False), ('뮤즈라이브', 0.25, False),
    ('잔디마당', 10.0, True), ('평화의 광장', 5.0, True), ('옥외', 5.0, True),
]
DEFAULT_START = {'weekday': 19 * 60 + 30, 'sat': 18 * 60, 'sun': 17 * 60}
DUR_MIN = 150


def venue_info(place: str):
    p = (place or '').replace(' ', '')
    for key, w, big in VENUES:
        if key.replace(' ', '') in p:
            return key, w, big
    return (place or '기타').strip(), 1.0, False


DOW_CH = '월화수목금토일'
EN_DOW = {'MON': '월', 'TUE': '화', 'WED': '수', 'THU': '목', 'FRI': '금', 'SAT': '토', 'SUN': '일'}


def _times(seg: str):
    """문자열 조각에서 시각(분)을 모두 찾는다."""
    out = []
    s = seg.upper()
    for m in re.finditer(r'(오전|오후|AM|PM)?\s*(\d{1,2})\s*(?::\s*(\d{2})|시\s*(?:(\d{1,2})\s*분|반)?)\s*(AM|PM)?', s):
        ap1, h, mm1, mm2, ap2 = m.groups()
        h = int(h); mm = int(mm1 or mm2 or 0)
        if '반' in m.group(0): mm = 30
        ap = ap1 or ap2
        if ap in ('오후', 'PM') and h < 12: h += 12
        if ap is None and 1 <= h <= 9: h += 12   # "7시" 같은 표기는 저녁 공연으로 본다
        if 9 <= h <= 23: out.append(h * 60 + mm)
    for m in re.finditer(r'(\d{1,2})\s*(AM|PM)', s):
        h = int(m.group(1)) + (12 if m.group(2) == 'PM' and int(m.group(1)) < 12 else 0)
        if 9 <= h <= 23 and h * 60 not in out: out.append(h * 60)
    return out


def parse_start_times(tm: str):
    """'토 오후 6시 / 일 오후 5시' → {'토':[1080], '일':[1020], '*':[...]}"""
    tm = (tm or '')
    for en, ko in EN_DOW.items():
        tm = re.sub(en, ko, tm, flags=re.I)
    tm = re.sub(r'\d{4}[.\-년]\s*\d{1,2}[.\-월]\s*\d{1,2}[.일]?', ' ', tm)  # 날짜 제거
    tm = re.sub(r'\d{1,2}\s*월\s*\d{1,2}\s*일', ' ', tm)
    tm = re.sub(r'\d{1,2}\s*[./]\s*\d{1,2}\s*\.?', ' ', tm)   # 11.28 같은 짧은 날짜
    tm = re.sub(r'(\d)\s*(월|일)(?![가-힣])', r'\1 ', tm)     # 남은 'N월', 'N일' 숫자 표기
    # 요일 표시('토', '(일)', '수목금', '토요일')마다 구간을 나눈다. 단어 속 글자(일반, 매일)는 제외.
    marks = list(re.finditer(r'(?<![가-힣])([월화수목금토일]{1,3})(?:요일)?(?![가-힣])', tm))
    res = {}

    def add(days, seg):
        ts = _times(seg)
        for d in days:
            res.setdefault(d, [])
            res[d] += [t for t in ts if t not in res[d]]

    if not marks:
        add(['*'], tm)
    else:
        add(['*'], tm[:marks[0].start()])
        for i, m in enumerate(marks):
            seg = tm[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(tm)]
            days = list(dict.fromkeys(m.group(1)))
            if not _times(seg) and i + 1 < len(marks):
                # '토, 일 18시'처럼 요일만 나열하고 시각을 뒤에 쓴 경우: 다음 시각을 함께 쓴다
                nxt = next((tm[mm.end(): marks[j + 1].start() if j + 1 < len(marks) else len(tm)]
                            for j, mm in enumerate(marks[i + 1:], i + 1)
                            if _times(tm[mm.end(): marks[j + 1].start() if j + 1 < len(marks) else len(tm)])), '')
                seg = nxt
            add(days, seg)
    return {k: v for k, v in res.items() if v}


def expand_events(events):
    """공연 목록(beginDt, endDt, tm, plc, title, ndTm) → 날짜별 회차 리스트."""
    rows = []
    for e in events:
        try:
            days = pd.date_range(e['beginDt'], e['endDt'])
        except Exception:
            continue
        if len(days) > 45:   # 장기 전시·상설 행사는 하루 영향이 작아 제외
            continue
        st = parse_start_times(e.get('tm', ''))
        venue, w, big = venue_info(e.get('plc', ''))
        dur = DUR_MIN
        m = re.search(r'(\d{2,3})\s*분', e.get('ndTm') or '')
        if m: dur = min(240, max(60, int(m.group(1)) + 15))
        for d in days:
            dch = DOW_CH[d.dayofweek]
            ts = st.get(dch) or st.get('*')
            if not ts:
                if st and any(k in DOW_CH for k in st):  # 요일이 지정됐는데 이 요일이 없으면 공연 없음
                    continue
                key = 'sat' if d.dayofweek == 5 else 'sun' if d.dayofweek == 6 or d in KR_HOL else 'weekday'
                ts = [DEFAULT_START[key]]
            for t in ts:
                rows.append(dict(date=d.normalize(), start=t, end=t + dur, venue=venue, w=w, big=big,
                                 title=re.sub(r'\s+', ' ', e.get('title', '')).strip(), place=(e.get('plc') or '').strip()))
    return pd.DataFrame(rows)


def calendar_feats(idx: pd.DatetimeIndex):
    f = pd.DataFrame(index=idx)
    f['hour'] = idx.hour
    f['dow'] = idx.dayofweek
    f['month'] = idx.month
    hol = np.array([d in KR_HOL for d in idx.date])
    f['offday'] = ((idx.dayofweek >= 5) | hol).astype(int)
    nxt = np.array([(pd.Timestamp(d) + pd.Timedelta(days=1)).date() in KR_HOL or (pd.Timestamp(d) + pd.Timedelta(days=1)).dayofweek >= 5 for d in idx.date])
    f['before_off'] = nxt.astype(int)
    return f


def event_feats(idx: pd.DatetimeIndex, ev: pd.DataFrame):
    """시각 t마다: 앞으로 0~3시간 안에 시작하는 공연 규모, 진행 중 규모, 끝난 지 1시간 이내 규모, 그날 총규모."""
    f = pd.DataFrame(0.0, index=idx, columns=['ev_pre', 'ev_on', 'ev_post', 'ev_day', 'ev_big_day'])
    if ev is None or ev.empty: return f
    by = {d: g for d, g in ev.groupby(ev['date'].dt.date)}
    for t in idx:
        g = by.get(t.date())
        if g is None: continue
        m = t.hour * 60 + 30
        f.at[t, 'ev_pre'] = g.loc[(g.start - m > 0) & (g.start - m <= 180), 'w'].sum()
        f.at[t, 'ev_on'] = g.loc[(g.start <= m) & (g.end > m), 'w'].sum()
        f.at[t, 'ev_post'] = g.loc[(g.end <= m) & (m - g.end < 60), 'w'].sum()
        uniq = g.drop_duplicates(['title', 'venue'])
        f.at[t, 'ev_day'] = uniq.w.sum()
        f.at[t, 'ev_big_day'] = uniq.big.sum()
    return f


def load_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def save_json(obj, p):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
