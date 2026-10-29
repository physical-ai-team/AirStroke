// AirStroke 그림판: gateway PC WebSocket(/ws/pc/{sid})으로 commands 를 받아 그린다.
// 테스트 모드(?mock=1): gateway 없이 mock.js 의 시나리오·마우스 입력이 같은 handleCommand 로 들어온다.

const COLORS = ['#1a1a1a', '#e53935', '#1e88e5', '#43a047', '#fb8c00', '#8e24aa'];
const ERASER_WIDTH = 60; // CSS px
const LABELS = { draw: '✏️ 그리기', move: '✌️ 이동', erase: '✋ 지우개', idle: '✊ 대기' };
const RECONNECT_MAX_MS = 5000;
const CLOSE_UNKNOWN_SESSION = 4404; // POST /api/sessions 로 만들지 않았거나 만료된 세션

const $ = (id) => document.getElementById(id);
const stage = $('stage'), board = $('board');
const paint = $('paint'), pctx = paint.getContext('2d');
const overlay = $('overlay'), octx = overlay.getContext('2d');

const pen = { color: COLORS[0], width: Number($('width').value) };
let aspect = 4 / 3; // /api/config 의 카메라 비율로 덮어씀

// 브라우저 ↔ gateway 계약(docs/03-protocol.md)의 PC WebSocket 경로
function wsUrl(sid) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws/pc/${encodeURIComponent(sid)}`;
}

// ---------- 그림 상태 ----------
// 선은 stroke 단위로 정규화 좌표(0~1)로 기록한다 (크기 변경 시 다시 그리기, 실행 취소)
const strokes = [];
let current = null; // 그리는 중인 stroke
let lastCmd = null; // 오버레이용 최신 명령

function toPx(p) { return [p.x * paint.width, p.y * paint.height]; }

function applyStyle(s) {
  pctx.globalCompositeOperation = s.mode === 'erase' ? 'destination-out' : 'source-over';
  pctx.strokeStyle = pctx.fillStyle = s.color;
  pctx.lineWidth = s.width * devicePixelRatio;
  pctx.lineCap = pctx.lineJoin = 'round';
}

function drawDot(s, p) {
  const [x, y] = toPx(p);
  applyStyle(s);
  pctx.beginPath();
  pctx.arc(x, y, pctx.lineWidth / 2, 0, Math.PI * 2);
  pctx.fill();
}

function drawSegment(s, a, b) {
  applyStyle(s);
  pctx.beginPath();
  pctx.moveTo(...toPx(a));
  pctx.lineTo(...toPx(b));
  pctx.stroke();
}

function redrawAll() {
  pctx.clearRect(0, 0, paint.width, paint.height);
  for (const s of strokes) {
    drawDot(s, s.points[0]);
    for (let i = 1; i < s.points.length; i++) drawSegment(s, s.points[i - 1], s.points[i]);
  }
}

// 커서 좌표는 카메라 기준 0~1 이므로 캔버스를 카메라 비율로 맞춰야 원이 타원이 되지 않는다
function resize() {
  const aw = stage.clientWidth - 32, ah = stage.clientHeight - 32;
  const w = Math.max(1, Math.min(aw, ah * aspect)), h = w / aspect;
  board.style.width = `${w}px`;
  board.style.height = `${h}px`;
  const pw = Math.round(w * devicePixelRatio), ph = Math.round(h * devicePixelRatio);
  if (paint.width === pw && paint.height === ph) return;
  paint.width = overlay.width = pw;
  paint.height = overlay.height = ph;
  redrawAll();
}
new ResizeObserver(resize).observe(stage);

// CommandMsg 하나 처리. draw 는 stroke_id 가 같으면 이어 긋고 바뀌면 새 선,
// erase 는 연속된 erase 명령을 한 stroke 로 묶는다 (실행 취소 단위)
function handleCommand(cmd) {
  lastCmd = cmd;
  const p = cmd.cursor;
  let key = null;
  if (cmd.action === 'draw' && cmd.stroke_id != null) key = `draw:${cmd.stroke_id}`;
  else if (cmd.action === 'erase') key = 'erase';
  if (!key || !p) {
    current = null;
    return;
  }
  if (!current || current.key !== key) {
    const erase = key === 'erase';
    current = {
      key, mode: erase ? 'erase' : 'draw', color: pen.color,
      width: erase ? ERASER_WIDTH : pen.width, points: [p],
    };
    strokes.push(current);
    drawDot(current, p);
    return;
  }
  drawSegment(current, current.points[current.points.length - 1], p);
  current.points.push(p);
}

function renderOverlay() {
  octx.clearRect(0, 0, overlay.width, overlay.height);
  const cmd = lastCmd;
  if (cmd && cmd.cursor) {
    const dpr = devicePixelRatio;
    const [x, y] = toPx(cmd.cursor);
    const r = (cmd.action === 'erase' ? ERASER_WIDTH / 2 : cmd.action === 'draw' ? 8 : 6) * dpr;
    octx.globalAlpha = cmd.action === 'move' ? 0.4 : 1;
    octx.lineWidth = 2 * dpr;
    octx.strokeStyle = cmd.action === 'draw' ? pen.color : '#36f';
    octx.beginPath();
    octx.arc(x, y, r, 0, Math.PI * 2);
    octx.stroke();
    octx.globalAlpha = 1;
    octx.font = `${18 * dpr}px system-ui, sans-serif`;
    octx.fillStyle = '#222';
    octx.fillText(LABELS[cmd.action] || cmd.action, x + r + 6 * dpr, y - r);
  }
  requestAnimationFrame(renderOverlay);
}
requestAnimationFrame(renderOverlay);

// ---------- 툴바 ----------
for (const color of COLORS) {
  const b = document.createElement('button');
  b.className = 'swatch';
  b.style.background = color;
  b.title = color;
  b.onclick = () => {
    pen.color = color;
    for (const el of document.querySelectorAll('.swatch')) el.classList.toggle('selected', el === b);
  };
  $('palette').append(b);
}
$('palette').firstChild.classList.add('selected');

$('width').oninput = (e) => {
  pen.width = Number(e.target.value);
  $('widthOut').textContent = pen.width;
};

function undo() {
  if (strokes.pop() === current) current = null;
  redrawAll();
}

function clearAll() {
  strokes.length = 0;
  current = null;
  redrawAll();
}

// 아래층(그림)만 흰 배경 위에 합쳐서 저장 (오버레이·투명 배경 제외)
function savePng() {
  const out = document.createElement('canvas');
  out.width = paint.width;
  out.height = paint.height;
  const ctx = out.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, out.width, out.height);
  ctx.drawImage(paint, 0, 0);
  const d = new Date(), pad = (n) => String(n).padStart(2, '0');
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-`
    + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  const a = document.createElement('a');
  a.download = `airstroke-${stamp}.png`;
  a.href = out.toDataURL('image/png');
  a.click();
}

$('undo').onclick = undo;
$('clear').onclick = clearAll;
$('save').onclick = savePng;
document.addEventListener('keydown', (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.target.tagName === 'INPUT') return;
  if (e.key === 'z') { e.preventDefault(); undo(); }
  if (e.key === 's') { e.preventDefault(); savePng(); }
});

// ---------- 통계 ----------
let cmdCount = 0;
setInterval(() => {
  $('stats').textContent = `commands ${cmdCount} fps · 선 ${strokes.length}개`;
  cmdCount = 0;
}, 1000);

function setState(text, cls) {
  $('state').textContent = text;
  $('dot').className = `dot ${cls || ''}`;
}

// ---------- WebSocket ----------
let ws = null, wantSid = null, retryMs = 500, retryTimer = null;

function connect(sid) {
  clearTimeout(retryTimer);
  if (ws) { ws.onclose = null; ws.close(); }
  wantSid = sid;
  setState(`연결 중… (${sid})`, 'wait');
  ws = new WebSocket(wsUrl(sid));
  ws.onopen = () => { retryMs = 500; setState(`연결됨 (${sid})`, 'ok'); };
  ws.onmessage = (ev) => {
    if (typeof ev.data !== 'string') return; // 바이너리 = PiP 영상 (다음 작업)
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    switch (msg.type) {
      case 'command': cmdCount++; handleCommand(msg.data); break;
      case 'ping':
        ws.send(JSON.stringify({ type: 'pong', id: msg.id, t_server: msg.t_server, t_client: Date.now() }));
        break;
      case 'status': $('qr').hidden = !!msg.mobile_connected; break;
      // landmarks, clock 은 3단계(뼈대·지연시간 표시)에서 처리
    }
  };
  ws.onclose = (ev) => {
    lastCmd = null; // 끊긴 동안 마지막 커서·라벨이 남지 않게
    current = null;
    $('qr').hidden = true;
    if (ev.code === CLOSE_UNKNOWN_SESSION) {
      setState(`세션 ${sid} 이(가) 없거나 만료됨 — '새 세션 만들기'를 누르세요`, '');
      return;
    }
    setState(`끊김 — ${Math.round(retryMs / 100) / 10}초 후 재연결`, '');
    retryTimer = setTimeout(() => connect(wantSid), retryMs);
    retryMs = Math.min(retryMs * 2, RECONNECT_MAX_MS);
  };
}

// ---------- 세션 UI ----------
function useSession(sid) {
  sid = sid.trim();
  if (!sid) return;
  $('sid').value = sid;
  const url = new URL(location.href);
  url.searchParams.set('s', sid);
  history.replaceState(null, '', url);
  // QR 은 status 메시지(mobile_connected=false)를 받으면 보인다
  $('qrImg').src = `/api/sessions/${encodeURIComponent(sid)}/qr.svg`;
  const code = document.createElement('code');
  code.textContent = `python tools/mock_commands.py --session ${sid}`;
  $('hint').replaceChildren('단독 개발: ', code);
  connect(sid);
}

async function createSession() {
  try {
    const res = await fetch('/api/sessions', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    useSession((await res.json()).session_id);
  } catch (e) {
    setState(`세션 생성 실패: ${e.message} — 세션 ID를 직접 입력하세요`, '');
  }
}

$('create').onclick = createSession;
$('connect').onclick = () => useSession($('sid').value);
$('sid').onkeydown = (e) => { if (e.key === 'Enter') useSession($('sid').value); };

// ---------- 시작 ----------
try {
  const res = await fetch('/api/config');
  const cam = res.ok ? (await res.json()).camera : null;
  if (cam && cam.width && cam.height) aspect = cam.width / cam.height;
} catch { /* gateway 없음 → 기본 4:3 */ }
resize();

const params = new URLSearchParams(location.search);
if (params.has('mock')) {
  document.body.classList.add('mock');
  setState('테스트 모드 (gateway 없음)', 'wait');
  $('hint').textContent = '왼쪽 드래그: 그리기 · 오른쪽 드래그: 지우개 · Ctrl+Z: 실행 취소';
  const { startMock } = await import('./mock.js');
  startMock({ target: board, button: $('scenario'), onCommand: (cmd) => { cmdCount++; handleCommand(cmd); } });
} else {
  // URL ?s=<sid> (폰 페이지와 같은 파라미터) 가 있으면 그 세션으로, 없으면 새로 만들어 연결
  const initial = params.get('s') || params.get('sid');
  if (initial) useSession(initial);
  else createSession();
}
