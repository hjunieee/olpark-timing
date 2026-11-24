'use strict';
const LV = ['한산', '보통', '붐빔', '혼잡', '매우 혼잡'];
const DOW = ['일', '월', '화', '수', '목', '금', '토'];
const $ = (s) => document.querySelector(s);
const state = { fc: null, stats: null, zones: null, byDate: {}, date: null, month: null };

const pad = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parse = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const kstToday = () => { const n = new Date(Date.now() + (9 * 60 + new Date().getTimezoneOffset()) * 60000); return ymd(n); };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n) => Math.round(n).toLocaleString('ko-KR');

function levelOf(cars, day = false) {
  const th = (day && state.fc.dayThresholds) || state.fc.thresholds; // 4 boundaries
  let i = 0; while (i < th.length && cars >= th[i]) i++;
  return i;
}

async function load() {
  const get = (f) => fetch(`data/${f}?v=${Date.now() >> 20}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const [fc, stats, zones] = await Promise.all([get('forecast.json'), get('stats.json'), get('zones.json')]);
  state.fc = fc; state.stats = stats; state.zones = zones;
  if (!fc) { $('#dayAdvice').textContent = '예보 데이터를 불러오지 못했습니다.'; return; }
  fc.days.forEach((d) => (state.byDate[d.date] = d));
  const today = kstToday();
  const [hTab, hDate] = location.hash.replace('#', '').split('/');   // 공유 링크: #day/2026-12-05
  state.date = state.byDate[hDate] ? hDate : state.byDate[today] ? today : fc.days[0].date;
  state.month = state.date.slice(0, 7);
  $('#datePick').min = fc.days[0].date; $('#datePick').max = fc.days[fc.days.length - 1].date;
  $('#genStamp').textContent = `예보 갱신: ${fc.generated} · 학습 데이터: ${fc.trainedOn}`;
  $('#legend').innerHTML = LV.map((n, i) => `<span><i class="lv${i}"></i>${n}</span>`).join('');
  renderDay(); renderMonth(); renderNow(); renderAbout();
  if (['day', 'month', 'now', 'about'].includes(hTab)) showTab(hTab);
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
  $('#dayLevel').innerHTML = `<span class="badge lv${lv}">${LV[lv]}</span> 최대 약 ${fmt(d.peak)}대`;
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
    adv = `${esc(e.place)}에서 ${esc(e.title)} 공연이 있습니다. 공연 시작 2시간 전부터 주차장이 빠르게 찹니다. ${s.good[0].h}시 무렵 도착하거나 대중교통(5·8호선 올림픽공원역, 8호선 몽촌토성역)을 권합니다.`;
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
    v, label: h % 3 === 0 ? `${h}` : '', tip: `${h}시 약 ${fmt(v)}대`, cls: `lv${levelOf(v)}`,
    mark: d.events.some((e) => e.startH === h) ? '🎤' : '',
  })));
  $('#chartNote').textContent = '가로축은 시각(0~23시), 막대는 그 시각 주차장에 머무는 예상 차량 대수입니다. 🎤는 공연 시작 시각입니다.';
}

function drawBars(sel, items, maxV) {
  const el = $(sel);
  const max = maxV || Math.max(...items.map((i) => i.v)) * 1.12 || 1;
  const step = max > 2000 ? 1000 : max > 800 ? 500 : 200;
  let gl = '';
  for (let g = step; g < max; g += step) gl += `<div class="gl" style="bottom:${22 + (g / max) * (el.clientHeight - 30)}px"><em>${fmt(g)}</em></div>`;
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
  if (!z) { $('#zonesNow').textContent = '구역 데이터를 불러오지 못했습니다.'; return; }
  const map = { '원활': 0, '혼잡': 3, '만차': 4 };
  if (z.now && z.now.zones.length) {
    $('#nowStamp').textContent = `기준 ${z.now.stamp}`;
    $('#zonesNow').innerHTML = z.now.zones.map((q) => `<div class="zone lv${map[q.level] ?? 1}"><b>${esc(q.zone)}</b>${esc(q.level)}${q.cars != null ? ` · ${fmt(q.cars)}대` : ''}</div>`).join('');
    $('#nowNote').textContent = z.now.note || '';
  } else {
    $('#zonesNow').innerHTML = '<p class="note">실시간 자료가 아직 없습니다.</p>';
  }
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

/* ---------- 데이터·정확도 ---------- */
function renderAbout() {
  const s = state.stats; if (!s) return;
  $('#metrics').innerHTML = s.metrics.map((m) => `<div class="metric"><b>${esc(m.value)}</b><span>${esc(m.label)}</span></div>`).join('');
  $('#metricNote').textContent = s.metricNote || '';
  if (s.effect) {
    drawBars('#effectChart', s.effect.map((e, i) => ({ v: e.v, label: e.label, tip: `${e.label}: 하루 최대 평균 ${fmt(e.v)}대 (${e.n}일)`, val: `${fmt(e.v)}대`, cls: `lv${Math.min(4, i)}` })));
    $('#effectNote').textContent = s.effectNote || '';
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
$('#calendar').addEventListener('click', (e) => { const b = e.target.closest('button.d'); if (b) { state.date = b.dataset.date; renderDay(); showTab('day'); } });
window.addEventListener('resize', () => { if ($('#tab-day').classList.contains('on')) renderDay(); });
load();
