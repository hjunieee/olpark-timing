"""검증 실험: (1) 7월 주 단위 교차검증 (2) 2025년 주차장 혼잡도 기록으로 독립 검증."""
import io, sys, pathlib
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score
import build
from build import *  # noqa

FE = [f for f in build.FEATS if f != 'temp']


def model(kind):
    if kind == 'hgb':
        return HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0, random_state=0)
    if kind == 'hgb_small':
        return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_leaf_nodes=8, min_samples_leaf=30, l2_regularization=2.0, random_state=0)


def fit_pred(kind, Xtr, ytr, Xte, resid):
    b_tr = baseline(Xtr, ytr, Xtr); b_te = baseline(Xtr, ytr, Xte)
    if kind == 'base': return b_te
    m = model(kind.replace('_res', ''))
    if resid:
        m.fit(Xtr[FE], ytr.values - b_tr); return np.clip(b_te + m.predict(Xte[FE]), 0, None)
    m.fit(Xtr[FE], ytr.values); return np.clip(m.predict(Xte[FE]), 0, None)


def main():
    io_ = load_io_file2024()
    y = hourly_occupancy(io_, '2024-07-01', '2024-07-31 23:00')
    events = fetch_events(['202407']); ev = expand_events(events)
    wx = weather_archive('2024-07-01', '2024-07-31')
    X = make_X(y.index, wx, ev)
    day = X.index.normalize()
    big = X.groupby(day).ev_big_day.transform('max') > 0
    folds = [(1, 7), (8, 14), (15, 21), (22, 31)]
    res = {}
    for kind, resid in [('base', 0), ('hgb', 0), ('hgb_small', 0), ('hgb', 1), ('hgb_small', 1)]:
        name = kind + ('_res' if resid else '')
        P = pd.Series(np.nan, index=y.index)
        for a, b_ in folds:
            te = (X.index.day >= a) & (X.index.day <= b_)
            P[te] = fit_pred(kind, X[~te], y[~te], X[te], resid)
        dm = (X.hour >= 9) & (X.hour <= 21)
        err = (P - y).abs()
        pk_t = y.groupby(day).max(); pk_p = P.groupby(day).max()
        bigd = big.groupby(day).max()
        res[name] = dict(mae=err[dm].mean(), mae_big=err[dm & big].mean(), mae_norm=err[dm & ~big].mean(),
                         peak=(abs(pk_p - pk_t) / pk_t).mean(), peak_big=(abs(pk_p - pk_t) / pk_t)[bigd].mean())
    r = pd.DataFrame(res).T
    print(r.round(3).to_string()); print('대형공연 날 수', int(big.groupby(day).max().sum()), '/ 시간 수', int((big & (X.hour >= 9) & (X.hour <= 21)).sum()))


if __name__ == '__main__':
    main()
