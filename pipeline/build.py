"""올팍타이밍 데이터 빌드: 학습 → 검증 → 앞으로 60일 예보 → site/data/*.json

사용: python pipeline/build.py [--source file2024|api2025]
- file2024: 공공데이터포털 파일데이터 '올림픽공원 입출차 정보'(2024-07, 로그인 불필요)
- api2025 : OpenAPI '올림픽공원 입출차정보(전체구역)'·연계 데이터(인증키 필요, fetch_api.py가 cache에 저장)
키는 환경변수 CULTURE_KEY로만 읽고, 결과 JSON에는 넣지 않는다.
"""
import argparse, datetime as dt, json, sys, time, urllib.request
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from common import *  # noqa

DATA_DIR = ROOT / 'raw'                # 공공데이터 원자료 사본
LAT, LON = 37.5207, 127.1214
UA = {'User-Agent': 'Mozilla/5.0 (olpark-timing data build)'}


# ---------------- 원자료 ----------------
def hourly_occupancy(io: pd.DataFrame, start, end):
    """입차·출차 시각 → 매시 정각 30분 기준 주차장에 머무는 차량 수."""
    io = io[(io.out >= io['in']) & ((io.out - io['in']) < pd.Timedelta('24h'))]
    idx = pd.date_range(start, end, freq='h')
    ins, outs = np.sort(io['in'].values), np.sort(io.out.values)
    t = (idx + pd.Timedelta('30min')).values
    occ = np.searchsorted(ins, t, 'right') - np.searchsorted(outs, t, 'right')
    return pd.Series(occ, index=idx, name='occ')


def load_io_file2024():
    df = pd.read_csv(DATA_DIR / 'dl' / '15138735.bin', encoding='cp949')
    return pd.DataFrame({'in': pd.to_datetime(df['입차일시']), 'out': pd.to_datetime(df['출차일시'])})


EV_KEEP = ('evtSeq', 'title', 'beginDt', 'endDt', 'tm', 'plc', 'ndTm')


def trim_events(raw):
    """공연 원자료에서 예측에 쓰는 칸만 남긴다(문의처 연락처·본문 HTML은 저장하지 않는다)."""
    return [[{k: e.get(k) for k in EV_KEEP} for e in part] if isinstance(part, list) else [] for part in raw]


def fetch_events(months):
    """올림픽공원 공연 일정(월별). 캐시가 있으면 쓴다. 지난 달은 캐시 고정, 이번 달 이후는 새로 받는다."""
    out = []
    now_ym = dt.date.today().strftime('%Y%m')
    for ym in months:
        p = DATA_DIR / 'events' / f'{ym}.json'
        if not p.exists() or ym >= now_ym:
            req = urllib.request.Request('https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListAjax.es',
                                         data=json.dumps({'nowYM': ym, 'plcCd': ''}).encode(),
                                         headers={**UA, 'Content-Type': 'application/json;charset=UTF-8'})
            try:
                p.parent.mkdir(exist_ok=True)
                raw = json.loads(urllib.request.urlopen(req, timeout=20).read())
                save_json(trim_events(raw), p); time.sleep(0.5)
            except Exception as e:
                print('공연 일정 받기 실패', ym, e)
        if p.exists():
            d = load_json(p)
            for part in d:
                out += part if isinstance(part, list) else []
    seen, uniq = set(), []
    for e in out:
        if e.get('evtSeq') in seen: continue
        seen.add(e.get('evtSeq')); uniq.append(e)
    return uniq


def weather_archive(start, end):
    p = CACHE / f'wx_{start}_{end}.json'
    if not p.exists():
        url = (f'https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={start}&end_date={end}'
               '&hourly=temperature_2m,precipitation&timezone=Asia%2FSeoul')
        p.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
    h = load_json(p)['hourly']
    w = pd.DataFrame({'temp': h['temperature_2m'], 'rain': h['precipitation']}, index=pd.to_datetime(h['time']))
    return w


def weather_forecast():
    """앞으로 16일 시간별 예보(Open-Meteo)."""
    url = (f'https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,precipitation,precipitation_probability'
           '&forecast_days=16&timezone=Asia%2FSeoul')
    try:
        h = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())['hourly']
        return pd.DataFrame({'temp': h['temperature_2m'], 'rain': h['precipitation'], 'pop': h['precipitation_probability']},
                            index=pd.to_datetime(h['time'])), 'Open-Meteo 예보'
    except Exception as e:
        print('날씨 예보 실패', e); return pd.DataFrame(columns=['temp', 'rain', 'pop']), ''


# ---------------- 특징 ----------------
FEATS = ['hour', 'dow', 'offday', 'before_off', 'temp', 'rain', 'rain3', 'ev_pre', 'ev_on', 'ev_post', 'ev_day', 'ev_big_day']


def make_X(idx, wx, ev):
    X = calendar_feats(idx).join(event_feats(idx, ev))
    w = wx.reindex(idx)
    X['temp'] = w['temp'].values
    X['rain'] = w['rain'].fillna(0).values
    X['rain3'] = w['rain'].fillna(0).rolling(3, min_periods=1).sum().values
    return X


def fit(X, y):
    feats = FEATS
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                      categorical_features=[feats.index('dow')], random_state=0)
    return m.fit(X[feats], y)


def baseline(train_X, train_y, test_X):
    """비교 기준: 같은 (휴일 여부, 시간) 평균."""
    tab = pd.DataFrame({'k': list(zip(train_X.offday, train_X.hour)), 'y': train_y.values}).groupby('k').y.mean()
    return np.array([tab.get(k, train_y.mean()) for k in zip(test_X.offday, test_X.hour)])


# ---------------- 메인 ----------------
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--source', default='file2024'); ap.add_argument('--days', type=int, default=60)
    a = ap.parse_args()

    global FEATS
    if a.source == 'file2024':
        FEATS = [f for f in FEATS if f != 'temp']   # 7월 기온만으로는 겨울 기온을 다룰 수 없다
        io = load_io_file2024(); t0, t1 = '2024-07-01', '2024-07-31'
        trained_on = '2024년 7월 올림픽공원 입출차 21만 건'
        test_days = 10
    else:
        import fetch_api
        io = fetch_api.load_io_2025(); t0, t1 = '2025-01-01', '2025-12-31'
        trained_on = '2025년 올림픽공원 입출차 1년치'
        test_days = 61   # 11~12월을 검증용으로 뗀다
    y = hourly_occupancy(io, t0, t1 + ' 23:00')
    months = sorted({d.strftime('%Y%m') for d in pd.date_range(t0, t1)})
    today = pd.Timestamp(dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(hours=9)).normalize()
    fut_idx = pd.date_range(today, today + pd.Timedelta(days=a.days) - pd.Timedelta('1h'), freq='h')
    fut_months = sorted({d.strftime('%Y%m') for d in fut_idx})
    events = fetch_events(months + fut_months)
    ev = expand_events(events)
    print('공연 회차', len(ev))

    wx = weather_archive(t0, t1)
    X = make_X(y.index, wx, ev)

    # 시간 순서로 나눠 검증 (뒤쪽 test_days 일)
    cut = y.index.max().normalize() - pd.Timedelta(days=test_days - 1)
    tr, te = y.index < cut, y.index >= cut
    m = fit(X[tr], y[tr])
    p = np.clip(m.predict(X[te][FEATS]), 0, None)
    b = baseline(X[tr], y[tr], X[te])
    yt = y[te].values
    day_mask = (X[te].hour >= 9) & (X[te].hour <= 21)
    mae, mae_b = np.mean(np.abs(p - yt)[day_mask]), np.mean(np.abs(b - yt)[day_mask])
    peak_t = pd.Series(yt, index=y.index[te]).groupby(lambda t: t.date()).max()
    peak_p = pd.Series(p, index=y.index[te]).groupby(lambda t: t.date()).max()
    peak_err = np.mean(np.abs(peak_p - peak_t) / peak_t)
    print(f'검증 MAE {mae:.0f}대 (기준 {mae_b:.0f}대), 일 최대 오차 {peak_err:.1%}')

    m = fit(X, y)  # 전체로 다시 학습

    # 혼잡 등급 경계: 학습 기간 9~21시 점유의 분위수
    day_occ = y[(y.index.hour >= 9) & (y.index.hour <= 21)]
    th = [float(np.percentile(day_occ, q)) for q in (40, 75, 92, 98.5)]
    peaks = y[(y.index.hour >= 6)].groupby(y.index[(y.index.hour >= 6)].date).max()
    typical = float(np.median(peaks))                      # 보통 날의 하루 최대 대수
    th_day = [typical * r for r in (0.9, 1.1, 1.3, 1.6)]   # 한산/보통/붐빔/혼잡/매우 혼잡 경계
    if a.source == 'file2024':
        mf0 = month_factors(train_month=7)
        k = float(np.mean(list(mf0.values())))   # 7월 기준 → 연평균 기준
        th = [t * k for t in th]; th_day = [t * k for t in th_day]

    # 미래 날씨: 예보(16일) + 그 뒤는 학습기간 같은 시간 평균 기온, 비 없음
    wf, wsrc = weather_forecast()
    clim = wx.groupby(wx.index.hour).temp.mean()
    wfut = pd.DataFrame(index=fut_idx)
    wfut['temp'] = wf['temp'].reindex(fut_idx) if len(wf) else np.nan
    wfut['rain'] = wf['rain'].reindex(fut_idx) if len(wf) else np.nan
    wfut['pop'] = wf['pop'].reindex(fut_idx) if len(wf) else np.nan
    has_wx = wfut['temp'].notna()
    wfut['temp'] = wfut['temp'].fillna(pd.Series(fut_idx.hour, index=fut_idx).map(clim))
    wfut['rain'] = wfut['rain'].fillna(0)
    Xf = make_X(fut_idx, wfut, ev)
    pf = np.clip(m.predict(Xf[FEATS]), 0, None)
    season_note = ''
    if a.source == 'file2024':
        mf = month_factors(train_month=7)
        pf = pf * np.array([mf[t.month] for t in fut_idx])
        season_note = '월별주차현황(2023~2025 평균)으로 달마다 방문 수요 차이를 보정했다.'

    days = []
    for d, g in pd.Series(pf, index=fut_idx).groupby(fut_idx.date):
        hours = [round(float(v)) for v in g.values]
        dts = pd.Timestamp(d)
        evd = ev[ev.date == dts] if len(ev) else ev
        evlist = []
        for _, r in (evd.sort_values('start').iterrows() if len(evd) else []):
            evlist.append({'title': r.title, 'place': r.place, 'start': f'{r.start // 60}:{r.start % 60:02d}',
                           'end': f'{min(r.end, 1439) // 60}:{min(r.end, 1439) % 60:02d}', 'startH': int(r.start // 60), 'big': bool(r.big)})
        wd = wfut.loc[g.index]
        ok = has_wx.loc[g.index]
        wxd = ({'tmax': float(wd.temp[ok].max()), 'tmin': float(wd.temp[ok].min()), 'rain': float(wd.rain[ok].sum()),
                'pop': int(np.nanmax(wd['pop'][ok])) if wd['pop'][ok].notna().any() else None, 'src': wsrc} if ok.sum() >= 12 else {})
        days.append({'date': str(d), 'peak': max(hours[6:23]), 'hours': hours, 'events': evlist, 'wx': wxd,
                     'holiday': KR_HOL.get(d) or ''})

    gen = (dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M KST')
    save_json({'generated': gen, 'trainedOn': trained_on, 'thresholds': th, 'dayThresholds': th_day, 'days': days}, SITE_DATA / 'forecast.json')

    # 공연 효과 요약 (학습 기간 실측)
    daily = pd.DataFrame({'peak': y.groupby(y.index.date).max()})
    dX = X.groupby(X.index.date).first()
    daily['off'] = dX.offday; daily['big'] = dX.ev_big_day > 0; daily['evw'] = dX.ev_day
    groups = [('평일·공연 없음/소규모', (daily.off == 0) & ~daily.big), ('평일·대형 공연', (daily.off == 0) & daily.big),
              ('휴일·대형 공연 없음', (daily.off == 1) & ~daily.big), ('휴일·대형 공연', (daily.off == 1) & daily.big)]
    effect = [{'label': l, 'v': float(daily.peak[mk].mean()), 'n': int(mk.sum())} for l, mk in groups if mk.sum() > 0]

    sources = [
        {'name': '올림픽공원 입출차 정보', 'org': '한국체육산업개발(주)', 'use': '시간대별 주차 대수 계산·학습', 'url': 'https://www.data.go.kr/data/15138735/fileData.do'},
        {'name': '올림픽공원 공연정보', 'org': '한국체육산업개발(주)', 'use': '공연 일정·시작 시각·공연장 (공공데이터포털 등록, 올림픽공원 홈페이지 제공)', 'url': 'https://www.data.go.kr/data/3037877/openapi.do'},
        {'name': '주차장 혼잡도 정보', 'org': '한국체육산업개발(주)', 'use': '구역별 만차 시간 패턴', 'url': 'https://www.data.go.kr/data/15164156/fileData.do'},
        {'name': '월별주차현황', 'org': '한국체육산업개발(주)', 'use': '계절별 방문 수요 보정', 'url': 'https://www.data.go.kr/data/15131671/fileData.do'},
        {'name': '과거 관측·16일 예보 날씨', 'org': 'Open-Meteo (CC BY 4.0)', 'use': '강수·기온 반영', 'url': 'https://open-meteo.com/'},
    ]
    stats = {
        'metrics': [
            {'value': f'{mae:.0f}대', 'label': '시간대별 평균 오차 (9~21시)'},
            ({'value': f'{(1 - mae / mae_b):.0%}', 'label': '단순 평균 대비 오차 감소'} if mae < mae_b * 0.98 else
             {'value': f'{mae_b:.0f}대', 'label': '비교 기준(휴일·시간대 평균) 오차'}),
            {'value': f'{peak_err:.0%}', 'label': '하루 최대 주차 대수 오차율'},
            {'value': f'{len(io):,}건', 'label': '학습한 입출차 기록'},
        ],
        'metricNote': f'학습 기간 마지막 {test_days}일을 떼어 두고, 앞부분만으로 학습한 모델이 그 기간을 얼마나 맞히는지 쟀습니다. '
                      f'비교 기준은 휴일 여부와 시간대만 보는 평균값(오차 {mae_b:.0f}대)입니다.',
        'seasonNote': season_note,
        'effect': effect,
        'effectNote': '학습 기간의 실제 하루 최대 주차 대수 평균입니다. 대형 공연은 KSPO DOME·핸드볼경기장·잔디마당 등 수천 명 규모 공연입니다.',
        'sources': sources,
    }
    save_json(stats, SITE_DATA / 'stats.json')
    build_zones()
    print('완료', gen, len(days), '일')


def month_factors(train_month):
    """월별주차현황(올림픽공원) 2023~2025 월평균 / 학습한 달 평균."""
    m = pd.read_csv(DATA_DIR / 'dl' / '15131671.bin', encoding='cp949')
    m = m[m['주차장소'] == '올림픽공원'].copy()
    m['mon'] = m['월'].str.replace('월', '').astype(int)
    avg = m.groupby('mon')['주차대수'].mean()
    return (avg / avg[train_month]).to_dict()


def build_zones():
    c = pd.read_csv(DATA_DIR / 'dl' / '15164156.bin', encoding='cp949')
    c['h'] = pd.to_datetime(c['등록시간'], format='%H:%M:%S', errors='coerce').dt.hour
    full = c[c['혼잡도'] == '만차']
    order = sorted(c['주차구역'].unique(), key=lambda z: (len(z), z))
    heat = {z: [int(((full['주차구역'] == z) & (full.h == h)).sum()) for h in range(24)] for z in order}
    last = c.sort_values(['등록일', '등록시간']).groupby('주차구역').tail(1)
    now = {'stamp': f"{last['등록일'].max()} (파일데이터 최신 기록)",
           'zones': [{'zone': r['주차구역'], 'level': r['혼잡도']} for _, r in last.set_index('주차구역').loc[order].reset_index().iterrows()],
           'note': '실시간 주차현황 OpenAPI가 연결되면 이 칸은 30분마다 갱신됩니다. 지금은 파일데이터의 구역별 마지막 기록입니다.'}
    rng = f"{c['등록일'].min()}~{c['등록일'].max()}"
    save_json({'heat': heat, 'heatNote': f'{rng} 동안 기록된 혼잡도 {len(c)}건 중 만차 {len(full)}건을 시간대별로 셌습니다. 진할수록 그 시간에 자주 찼습니다.',
               'now': now}, SITE_DATA / 'zones.json')


if __name__ == '__main__':
    main()
