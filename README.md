# 올팍타이밍

올림픽공원 시간대별 주차 혼잡 예보·방문 시간 추천 서비스.
2026년 한국체육산업개발(주) 공공데이터 활용 경진대회 출품작.

- 서비스: https://hjunieee.github.io/olpark-timing/
- 구조: `pipeline/build.py`가 공공데이터로 예측 모델을 학습하고 앞으로 60일 예보를 `site/data/*.json`에 쓴다. `site/`는 정적 웹페이지다.
- 갱신: GitHub Actions가 매일 06:00(KST)에 다시 계산한다. 인증키는 저장소 Secret `CULTURE_KEY`로만 읽고, 결과물에는 넣지 않는다.

## 사용한 공공데이터
- 한국체육산업개발(주) 올림픽공원 입출차 정보, 주차장 혼잡도 정보, 월별주차현황 (공공데이터포털 파일데이터)
- 한국체육산업개발(주) 올림픽공원 공연정보 (공공데이터포털 3037877, 올림픽공원 홈페이지 공연 일정)
- Open-Meteo 과거 관측·예보 (날씨)

## 로컬 실행
```
pip install -r requirements.txt
python pipeline/build.py
python -m http.server 8000 --directory site
```
