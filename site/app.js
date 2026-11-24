'use strict';
const LV = ['여유', '보통', '다소 혼잡', '혼잡', '만차'];
const DOW = ['일', '월', '화', '수', '목', '금', '토'];
const $ = (s) => document.querySelector(s);
const state = { fc: null, stats: null, zones: null, live: null, byDate: {}, date: null, month: null };

const pad = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parse = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const kstToday = () => { const n = new Date(Date.now() + (9 * 60 + new Date().getTimezoneOffset()) * 60000); return ymd(n); };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n) => Math.round(n).toLocaleString('ko-KR');
const pct = (v) => (state.fc && state.fc.capacity ? ` (정원의 ${Math.round(v / state.fc.capacity * 100)}%)` : '');
const riskText = (d) => (d.risk != null ? `만차 가능성 ${Math.round(d.risk * 100)}%` : '');
const pctOf = (v) => (state.fc && state.fc.capacity ? Math.round(v / state.fc.capacity * 100) : null);
const arriveText = (hours) => bestSlots(hours).good.map((g) => `${g.h}~${g.h + 2}시`).join(' 또는 ');

function levelOf(cars, day = false) {
  const th = (day && state.fc.dayThresholds) || state.fc.thresholds; // 4 boundaries
  let i = 0; while (i < th.length && cars >= th[i]) i++;
  return i;
}

async function load() {
  const get = (f) => fetch(`data/${f}?v=${Date.now() >> 20}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const [fc, stats, zones, live] = await Promise.all([get('forecast.json'), get('stats.json'), get('zones.json'),
    fetch(`data/now.json?t=${Date.now()}`).then((r) => (r.ok ? r.json() : null)).catch(() => null)]);
  state.fc = fc; state.stats = stats; state.zones = zones; state.live = live;
  if (!fc) { $('#dayAdvice').textContent = '예보 데이터를 불러오지 못했습니다.'; return; }
  fc.days.forEach((d) => (state.byDate[d.date] = d));
  const today = kstToday();
  const [hTab, hDate] = location.hash.replace('#', '').split('/');   // 공유 링크: #day/2026-12-05
  state.date = state.byDate[hDate] ? hDate : state.byDate[today] ? today : fc.days[0].date;
  state.month = state.date.slice(0, 7);
  $('#datePick').min = fc.days[0].date; $('#datePick').max = fc.days[fc.days.length - 1].date;
  $('#genStamp').textContent = `예보 갱신: ${fc.generated} · 학습 데이터: ${fc.trainedOn}`;
  $('#legend').innerHTML = LV.map((n, i) => `<span><i class="lv${i}"></i>${n}</span>`).join('');
  renderDay(); renderMonth(); renderNow(); renderLive(); renderOps(); renderAbout();
  if (['day', 'month', 'now', 'ops', 'about'].includes(hTab)) showTab(hTab);
}

/* ---------- 날짜별 예보 ---------- */
function bestSlots(hours) {
  // 9~20시 중 2시간 창 평균이 가장 낮은 곳과 가장 높은 곳
  const win = [];
  for (let h = 9; h <= 19; h++) win.push({ h, v: (hours[h] + hours[h + 1]) / 2 });
  const sorted = [...win].sort((a, b) => a.v - b.v);
  return { good: sorted.slice(0, 2).sort((a, b) => a.h - b.h), bad: sorted[sorted.length - 1] };
}

function renderDay() {
  const d = state.byDate[state.date]; if (!d) return;
  const dt = parse(d.date);
  $('#datePick').value = d.date;
  const isToday = d.date === kstToday();
  $('#dateLabel').textContent = `${dt.getMonth() + 1}월 ${dt.getDate()}일 (${DOW[dt.getDay()]})${d.holiday ? ' · ' + d.holiday : ''}${isToday ? ' · 오늘' : ''}`;
  const lv = levelOf(d.peak, true);
  $('#dayLevel').innerHTML = `<span class="badge lv${lv}">${LV[lv]}</span> 최대 약 ${fmt(d.peak)}대<small class="pct">${pct(d.peak)}${d.risk != null ? ' · ' + riskText(d) : ''}</small>`;
  const w = d.wx || {};
  $('#dayWx').innerHTML = w.tmax != null
    ? `<b>${Math.round(w.tmin)}° / ${Math.round(w.tmax)}°</b>${w.rain > 0.5 ? `비 ${w.rain.toFixed(0)}mm` : w.pop != null ? `강수확률 ${w.pop}%` : '비 소식 없음'}<br><small>${esc(w.src || '')}</small>`
    : '<small>날씨 예보 전<br>(평년 기준)</small>';

  const s = bestSlots(d.hours);
  const peakH = d.hours.indexOf(Math.max(...d.hours.slice(6, 23)));
  const bigEv = d.events.filter((e) => e.big);
  let adv;
  if (bigEv.length) {
    const e = bigEv[0];
    const h0 = Math.max(0, e.startH - 2), pre = d.hours[h0];
    adv = `${esc(e.place)}에서 ${esc(e.title)} 공연(${esc(e.start)})이 있습니다.<br><b>공연 관객</b>: 시작 2시간 전(${h0}시)에 이미 약 ${fmt(pre)}대${pctOf(pre) != null ? `(정원의 ${pctOf(pre)}%)` : ''}로 예상됩니다. ${d.risk != null ? riskText(d) + '. ' : ''}대중교통(5·8호선 올림픽공원역, 8호선 몽촌토성역)을 권하고, 차로 오면 ${Math.max(9, h0 - 1)}시 전에 도착하세요.<br><b>산책·운동 방문객</b>: ${arriveText(d.hours)}이 여유롭습니다.`;
  } else if (lv >= 3) {
    adv = `평소보다 붐비는 날입니다. ${peakH}시 전후가 가장 붐빕니다. ${s.good[0].h}시 무렵 도착을 권합니다.`;
  } else if (lv === 2) {
    adv = `조금 붐비는 날입니다. ${peakH}시 전후가 가장 붐비고, ${s.good[0].h}시 이후가 여유롭습니다.`;
  } else {
    adv = `비교적 여유로운 날입니다. 가장 붐비는 시간은 ${peakH}시 전후입니다.`;
  }
  $('#dayAdvice').innerHTML = adv;
  $('#bestSlots').innerHTML =
    s.good.map((g) => `<div class="slot good">추천 도착<b>${g.h}:00~${g.h + 2}:00</b>약 ${fmt(g.v)}대</div>`).join('') +
    `<div class="slot bad">피할 시간<b>${s.bad.h}:00~${s.bad.h + 2}:00</b>약 ${fmt(s.bad.v)}대</div>`;

  $('#dayEvents').innerHTML = d.events.length
    ? d.events.map((e) => `<li><span class="t">${esc(e.start || '종일')}</span><span>${esc(e.title)}</span><span class="p">${esc(e.place)}${e.end ? ' · 종료 예상 ' + esc(e.end) : ''}</span></li>`).join('')
    : '<li><span class="none">등록된 공연이 없습니다.</span></li>';

  drawBars('#hourChart', d.hours.map((v, h) => ({
    v, label: h % 3 === 0 ? `${h}` : '', tip: `${h}시 약 ${fmt(v)}대${pct(v)}`, cls: `lv${levelOf(v)}`,
    mark: d.events.some((e) => e.startH === h) ? '🎤' : '',
  })), Math.max(...d.hours, state.fc.capacity || 0) * 1.12, state.fc.capacity);
  $('#chartNote').textContent = `가로축은 시각(0~23시), 막대는 그 시각 ${state.fc.scope || '주차장'}에 머무는 예상 차량 대수입니다. 점선은 정원(${fmt(state.fc.capacity || 0)}대)입니다. 🎤는 공연 시작 시각입니다.`;
}

function drawBars(sel, items, maxV, capLine) {
  const el = $(sel);
  const max = maxV || Math.max(...items.map((i) => i.v)) * 1.12 || 1;
  const step = max > 2000 ? 1000 : max > 800 ? 500 : 200;
  let gl = '';
  for (let g = step; g < max; g += step) gl += `<div class="gl" style="bottom:${22 + (g / max) * (el.clientHeight - 30)}px"><em>${fmt(g)}</em></div>`;
  if (capLine) gl += `<div class="capline" style="bottom:${22 + (capLine / max) * (el.clientHeight - 30)}px"><em>정원 ${fmt(capLine)}</em></div>`;
  el.innerHTML = gl + items.map((i) =>
    `<div class="bar ${i.cls}" tabindex="0" data-tip="${esc(i.tip)}" style="height:${Math.max(1, (i.v / max) * 100)}%">${i.mark ? `<i class="ev">${i.mark}</i>` : ''}${i.val ? `<b class="val">${esc(i.val)}</b>` : ''}<span>${esc(i.label)}</span></div>`).join('');
}

/* ---------- 달력 ---------- */
function renderMonth() {
  const [y, m] = state.month.split('-').map(Number);
  $('#monthTitle').textContent = `${y}년 ${m}월`;
  const first = new Date(y, m - 1, 1), days = new Date(y, m, 0).getDate();
  let html = DOW.map((d) => `<div class="dh">${d}</div>`).join('');
  for (let i = 0; i < first.getDay(); i++) html += '<div class="d empty"></div>';
  const today = kstToday();
  for (let i = 1; i <= days; i++) {
    const key = `${y}-${pad(m)}-${pad(i)}`, d = state.byDate[key];
    if (!d) { html += `<div class="d nodata"><span class="n">${i}</span></div>`; continue; }
    const lv = levelOf(d.peak, true);
    const ev = d.events.find((e) => e.big) || d.events[0];
    html += `<button class="d lv${lv}${key === today ? ' today' : ''}" data-date="${key}" title="${LV[lv]} · 최대 ${fmt(d.peak)}대"><span class="n">${i}${d.events.length ? ' ●' : ''}</span><span class="e">${ev ? esc(ev.title) : ''}</span></button>`;
  }
  $('#calendar').innerHTML = html;
}

/* ---------- 실시간·구역 ---------- */
function renderNow() {
  const z = state.zones;
  if (!z) { $('#zoneHeat').textContent = '구역 데이터를 불러오지 못했습니다.'; return; }
  const hrs = [...Array(24).keys()].filter((h) => h >= 7);
  const zs = Object.keys(z.heat);
  const mx = Math.max(1, ...zs.flatMap((k) => z.heat[k]));
  let t = '<table><tr><th class="z"></th>' + hrs.map((h) => `<th>${h % 2 ? '' : h}</th>`).join('') + '</tr>';
  zs.forEach((k) => {
    t += `<tr><th class="z">${esc(k)}</th>` + hrs.map((h) => {
      const v = z.heat[k][h], a = v / mx;
      return `<td title="${esc(k)} ${h}시 만차 기록 ${v}회" style="background:color-mix(in srgb, var(--l4) ${Math.round(a * 100)}%, var(--bg))"></td>`;
    }).join('') + '</tr>';
  });
  $('#zoneHeat').innerHTML = t + '</table><p class="note">' + esc(z.heatNote || '') + '</p>';
}

/* ---------- 실시간 주차 대수 ---------- */
function renderLive() {
  const L = state.live;
  if (!L) { $('#live').innerHTML = '<p class="note">실시간 값을 아직 받지 못했습니다. 30분마다 다시 받습니다.</p>'; return; }
  const r = L.parked / L.capacity, lv = r >= 0.9 ? 4 : r >= 0.7 ? 3 : r >= 0.5 ? 2 : r >= 0.3 ? 1 : 0;
  $('#liveStamp').textContent = `${L.stamp} 기준${L.error ? ' · ' + L.error : ''}`;
  $('#live').innerHTML = `<div class="live"><b>${fmt(L.parked)}대</b><span class="cap">/ ${fmt(L.capacity)}대 (동2문·남2문·북2문)</span>
    <span class="badge lv${lv}">이용률 ${Math.round(r * 100)}%</span></div>
    <div class="meter"><i class="lv${lv}" style="width:${Math.min(100, r * 100)}%"></i></div>`;
  const today = kstToday(), lg = (L.log || []).slice(-48);
  $('#liveChart').style.display = lg.length > 1 ? '' : 'none';
  if (lg.length > 1) drawBars('#liveChart', lg.map((x, i) => ({ v: x.n, label: i % 6 ? '' : x.t.slice(11), tip: `${x.t} ${fmt(x.n)}대`, val: '', cls: `lv${Math.min(4, Math.floor(x.n / L.capacity / 0.25))}` })));
  const ap = (L.agencyPred || []).map((x) => `${x.t.slice(5)} ${x.rate}%`).join(', ');
  $('#liveNote').textContent = `${L.source}. 기관이 공개하는 값을 30분마다 받습니다. 장기 주차 차량은 출차 기록이 없어 실제보다 많게 잡힐 수 있습니다(기관 안내).` +
    (ap ? ` 기관의 주말 공연 시간 예상 이용률: ${ap}.` : '');
}

/* ---------- 기관 운영 ---------- */
const TRANSIT = '대중교통(5·8호선 올림픽공원역, 8호선 몽촌토성역)';
function busyWindow(hours, th) {
  let s = -1, e = -1;
  for (let h = 7; h <= 22; h++) if (hours[h] >= th) { if (s < 0) s = h; e = h; }
  return s < 0 ? null : [s, e + 1];
}
function opsDays() {
  const th = state.fc.thresholds;          // 시간 단위 등급 경계
  return state.fc.days.map((d) => {
    const lv = levelOf(d.peak, true), big = d.events.filter((e) => e.big);
    const win = busyWindow(d.hours, th[2]) || busyWindow(d.hours, th[1]);
    return { d, lv, big, win };
  }).filter((x) => x.lv >= 3 || (x.d.risk || 0) >= 0.3);
}
function noticeText(x) {
  const dt = parse(x.d.date), md = `${dt.getMonth() + 1}월 ${dt.getDate()}일(${DOW[dt.getDay()]})`;
  const w = x.win ? `${x.win[0]}~${x.win[1]}시` : '오후';
  const ev = x.big.length ? ` ${x.big[0].place}에서 '${x.big[0].title}' 공연이 있습니다.` : '';
  return `[주차 혼잡 예보] ${md} ${w} 올림픽공원 주차장(${state.fc.scope || '주요 주차장'})이 ${LV[x.lv]}${x.lv === 4 ? '될' : '할'} 것으로 예상됩니다(최대 약 ${fmt(x.d.peak)}대${pct(x.d.peak)}).${ev}${x.big.length ? ` 공연 관람객께서는 ${TRANSIT}을 이용해 주시고, 차량은 공연 시작 3시간 전까지 도착해 주시기 바랍니다. 공원 산책·운동 방문은 ${arriveText(x.d.hours)}을 권합니다.` : ` 방문 시 ${TRANSIT}을 이용해 주시고, 차량은 ${arriveText(x.d.hours)}에 도착하시기 바랍니다.`}`;
}
function renderOps() {
  const list = opsDays();
  if (!list.length) { $('#opsList').innerHTML = '<p class="note">앞으로 60일 동안 혼잡 이상으로 예상되는 날이 없습니다.</p>'; return; }
  $('#opsList').innerHTML = list.map((x, i) => {
    const dt = parse(x.d.date), w = x.win;
    const acts = [];
    if (w) acts.push(`주차 안내 인력: <b>${Math.max(7, w[0] - 1)}~${w[1]}시</b> 증원 (예상 최대 ${fmt(x.d.peak)}대${pct(x.d.peak)})`);
    if (x.lv >= 4 || (x.d.risk || 0) >= 0.4) acts.push(`임시 주차장 개방·진입 통제 계획 준비 (${riskText(x.d)})`);
    if (x.big.length) acts.push(`공연 종료 예상 ${x.big.map((e) => e.end).join('·')} 전후 출차 유도`);
    acts.push('3일 전 홈페이지 핫뉴스·SNS 공지 (아래 문안)');
    return `<div class="ops"><h3><span class="badge lv${x.lv}">${LV[x.lv]}</span>${dt.getMonth() + 1}월 ${dt.getDate()}일 (${DOW[dt.getDay()]})${x.d.risk != null ? ` · <small>${riskText(x.d)}</small>` : ''}${x.d.holiday ? ' · ' + esc(x.d.holiday) : ''}
      <a href="#day/${x.d.date}" data-go="${x.d.date}">시간대별 보기</a></h3>
      ${x.big.length ? `<div class="note">${x.big.map((e) => `${esc(e.start)} ${esc(e.place)} · ${esc(e.title)}`).join('<br>')}</div>` : ''}
      <ul>${acts.map((a) => `<li>${a}</li>`).join('')}</ul>
      <textarea readonly id="nt${i}">${esc(noticeText(x))}</textarea>
      <button class="nav wide copy" data-copy="nt${i}">공지 문안 복사</button></div>`;
  }).join('');
}
function download(name, text, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function icsText() {
  const z = (n) => String(n).padStart(2, '0'), stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
  const ev = opsDays().filter((x) => x.win).map((x) => {
    const d = x.d.date.replace(/-/g, '');
    return ['BEGIN:VEVENT', `UID:olpark-${d}@olpark-timing`, `DTSTAMP:${stamp}`,
      `DTSTART;TZID=Asia/Seoul:${d}T${z(Math.max(7, x.win[0] - 1))}0000`, `DTEND;TZID=Asia/Seoul:${d}T${z(Math.min(23, x.win[1]))}0000`,
      `SUMMARY:[올팍타이밍] 주차 ${LV[x.lv]} 예상 (최대 ${Math.round(x.d.peak)}대)`,
      `DESCRIPTION:${noticeText(x).replace(/[,;]/g, ' ')}`, 'END:VEVENT'].join('\r\n');
  });
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//olpark-timing//KO', 'CALSCALE:GREGORIAN', ...ev, 'END:VCALENDAR'].join('\r\n');
}
function csvText() {
  const rows = ['날짜,시각,예상 주차 대수,하루 등급,공연'];
  state.fc.days.forEach((d) => d.hours.forEach((v, h) => rows.push(
    `${d.date},${h},${v},${LV[levelOf(d.peak, true)]},"${d.events.filter((e) => e.big).map((e) => e.title.replace(/"/g, "'")).join(' / ')}"`)));
  return '\ufeff' + rows.join('\n');
}

/* ---------- 데이터·정확도 ---------- */
function renderAbout() {
  const s = state.stats; if (!s) return;
  $('#metrics').innerHTML = s.metrics.map((m) => `<div class="metric"><b>${esc(m.value)}</b><span>${esc(m.label)}</span></div>`).join('');
  $('#metricNote').textContent = s.metricNote || '';
  if (s.effect) {
    drawBars('#effectChart', s.effect.map((e, i) => ({ v: e.v, label: e.label, tip: `${e.label}: 하루 최대 평균 ${fmt(e.v)}대 (${e.n}일)`, val: `${fmt(e.v)}대`, cls: `lv${Math.min(4, i)}` })));
    $('#effectNote').textContent = s.effectNote || '';
  }
  if (s.impact) {
    const I = s.impact, a = I.sim[0], b = I.sim[1];
    $('#impact').innerHTML = [
      [`${I.fullDays}일`, `2025년 만차 날(정원 90% 이상), 그중 휴일 ${I.fullDaysOff}일`],
      [`${I.overCapHours}시간`, '정원 2,200대를 넘긴 시간'],
      [`${Math.round(a.red * 100)}%`, `붐비는 시간 도착 차량 ${a.share * 100}%가 추천 시간으로 옮기면 줄어드는 정원 초과량`],
      [`${Math.round(b.red * 100)}%`, `${b.share * 100}%가 옮기면`],
    ].map(([v, l]) => `<div class="metric"><b>${v}</b><span>${l}</span></div>`).join('');
    $('#impactNote').textContent = `모의 계산입니다. ${I.method} 정원 초과량은 정원을 넘은 차량 수를 시간마다 더한 값(${fmt(a.excess0)}대·시간)입니다.`;
  }
  if (s.monthly) {
    const mx = Math.max(...s.monthly.map((x) => x.v));
    drawBars('#monthlyChart', s.monthly.map((x) => ({ v: x.v / 1000, label: x.label, tip: `${x.label} 평균 ${fmt(x.v)}대`, val: '', cls: `lv${Math.min(4, Math.max(0, Math.round((x.v / mx - 0.55) * 9)))}` })));
    $('#monthlyNote').textContent = s.monthlyNote || '';
  }
  $('#sources').innerHTML = s.sources.map((x) => `<tr><td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a>` : esc(x.name)}</td><td>${esc(x.org)}</td><td>${esc(x.use)}</td></tr>`).join('');
}

/* ---------- 이벤트 ---------- */
function showTab(t) {
  document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', b.dataset.tab === t));
  document.querySelectorAll('.tab').forEach((s) => s.classList.toggle('on', s.id === 'tab-' + t));
  history.replaceState(null, '', '#' + t);
  if (t === 'about') renderAbout();
  if (t === 'day') renderDay();
  if (t === 'now') renderLive();
}
document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));
function moveDay(n) {
  const d = parse(state.date); d.setDate(d.getDate() + n); const k = ymd(d);
  if (state.byDate[k]) { state.date = k; state.month = k.slice(0, 7); renderDay(); renderMonth(); }
}
$('#prevDay').onclick = () => moveDay(-1);
$('#nextDay').onclick = () => moveDay(1);
$('#datePick').onchange = (e) => { if (state.byDate[e.target.value]) { state.date = e.target.value; state.month = state.date.slice(0, 7); renderDay(); renderMonth(); } };
document.querySelectorAll('.quick button').forEach((b) => b.onclick = () => {
  const t = parse(kstToday());
  const n = b.dataset.q === 'sat' ? (6 - t.getDay() + 7) % 7 : Number(b.dataset.q);
  t.setDate(t.getDate() + n); const k = ymd(t);
  if (state.byDate[k]) { state.date = k; state.month = k.slice(0, 7); renderDay(); renderMonth(); }
});
$('#prevMonth').onclick = () => { const [y, m] = state.month.split('-').map(Number); const d = new Date(y, m - 2, 1); state.month = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; renderMonth(); };
$('#nextMonth').onclick = () => { const [y, m] = state.month.split('-').map(Number); const d = new Date(y, m, 1); state.month = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; renderMonth(); };
$('#opsList').addEventListener('click', (e) => {
  const c = e.target.closest('[data-copy]');
  if (c) { const t = $('#' + c.dataset.copy); t.select(); navigator.clipboard?.writeText(t.value); c.textContent = '복사했습니다'; }
  const g = e.target.closest('[data-go]');
  if (g) { e.preventDefault(); state.date = g.dataset.go; state.month = state.date.slice(0, 7); renderDay(); renderMonth(); showTab('day'); }
});
$('#dlIcs').onclick = () => download('olpark-timing.ics', icsText(), 'text/calendar');
$('#dlCsv').onclick = () => download('olpark-timing.csv', csvText(), 'text/csv');
$('#calendar').addEventListener('click', (e) => { const b = e.target.closest('button.d'); if (b) { state.date = b.dataset.date; renderDay(); showTab('day'); } });
window.addEventListener('resize', () => { if ($('#tab-day').classList.contains('on')) renderDay(); });
load();
