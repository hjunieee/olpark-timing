"""공익 효과 모의 계산: 만차일에 방문객 일부가 추천 시간으로 옮기면 정원 초과가 얼마나 줄어드는지(raw/impact_2025.json). 입출차 캐시가 필요하다."""
import sys, json, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_api, pandas as pd, numpy as np
from build import hourly_occupancy, CAP, MAIN_GATES, load_json, DATA_DIR
from common import KR_HOL
d = load_json(DATA_DIR / 'occ_2025.json'); valid = set(d['validDays'])
io = fetch_api.load_io_2025()
io = io[io.gin.str.extract(r'^(\S+?문)')[0].isin(MAIN_GATES)]
io = io[(io.out >= io['in']) & ((io.out - io['in']) < pd.Timedelta('24h'))].copy()
io['day'] = io['in'].dt.normalize(); io = io[io.day.dt.strftime('%Y-%m-%d').isin(valid)]
y = hourly_occupancy(io, '2025-01-01', '2025-12-31 23:00'); y = y[y.index.normalize().strftime('%Y-%m-%d').isin(valid)]
over = y[y >= CAP]; full_days = sorted(set(y[y >= 0.9 * CAP].index.normalize()))
print('정원 초과 시간', len(over), '90%이상 시간', int((y >= 0.9 * CAP).sum()), '만차일', len(full_days))
fd = pd.DataFrame({'d': full_days}); fd['off'] = [x.dayofweek >= 5 or x in KR_HOL for x in fd.d]
print('만차일 중 휴일', int(fd.off.sum()))
rng = np.random.default_rng(0)
def excess(occ): return float(np.clip(occ - CAP, 0, None).sum())
res = {}
for share in (0.1, 0.2):
    ex0 = ex1 = h0 = h1 = 0
    for day in full_days:
        sub = io[io.day == day].copy()
        occ = hourly_occupancy(sub, day, day + pd.Timedelta('23h'))
        busy = occ[occ >= 0.9 * CAP].index.hour
        win = [(h, occ.iloc[h:h + 2].mean()) for h in range(9, 20)]
        best = min(win, key=lambda x: x[1])[0]
        m = sub['in'].dt.hour.isin(busy)
        idx = sub[m].sample(frac=share, random_state=1).index
        dur = sub.loc[idx, 'out'] - sub.loc[idx, 'in']
        new_in = (day + pd.Timedelta(hours=best) + pd.to_timedelta(rng.uniform(0, 7200, len(idx)).round(), unit='s')).astype(sub['in'].dtype)
        sub.loc[idx, 'in'] = new_in.values; sub.loc[idx, 'out'] = (new_in + dur.values).values
        occ2 = hourly_occupancy(sub, day, day + pd.Timedelta('23h'))
        ex0 += excess(occ); ex1 += excess(occ2); h0 += int((occ >= CAP).sum()); h1 += int((occ2 >= CAP).sum())
    res[share] = dict(excess0=round(ex0), excess1=round(ex1), red=round(1 - ex1 / ex0, 3), overH0=h0, overH1=h1)
print(res)
