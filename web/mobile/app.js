/*
 * AirStroke 폰 카메라 페이지 (담당: 박민성)
 *
 * 역할: 폰 카메라 영상을 JPEG로 인코딩해 gateway로 보낸다.
 *   - URL ?s={sid} 에서 세션을 읽어 wss://…/ws/mobile/{sid} 로 연결
 *   - 해상도·fps·JPEG 품질·max_inflight_frames 는 GET /api/config 에서 받는다(하드코딩 금지)
 *   - 프레임 = [4바이트 big-endian 헤더 길이 N][N바이트 JSON 헤더][JPEG]
 *     헤더 {"seq", "capture_ts"(폰 시계 ms), "mirror"(전면 카메라면 true)}
 *   - ack 받지 않은 프레임이 max_inflight_frames 장이면 새 프레임은 버린다
 *   - ping 을 받으면 즉시 pong 으로 답한다(시계 동기화)
 *   - 탭이 백그라운드로 가면 캡처를 멈추고, 돌아오면 다시 연다
 *   - 1초마다 통계를 쌓아 "측정 CSV" 버튼으로 내려받는다(디바이스·네트워크 측정용)
 *   - 시연 모드: 통계를 한 줄로 접고 미리보기를 줄인다. 배터리 잔량을 표시한다(지원 시)
 * 계약: docs/03-protocol.md "브라우저 ↔ gateway 계약", 요구사항: docs/05-ui.md
 *
 * 실행: gateway가 /mobile/ 로 서빙한다. PC 그림판의 QR을 폰으로 스캔하면 열린다.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const els = {
  video: $('video'),
  notice: $('notice'),
  encoder: $('encoder'),
  btnStart: $('btn-start'),
  btnFlip: $('btn-flip'),
  conn: $('st-conn'),
  sid: $('st-sid'),
  cam: $('st-cam'),
  fps: $('st-fps'),
  sent: $('st-sent'),
  drop: $('st-drop'),
  inflight: $('st-inflight'),
  ack: $('st-ack'),
  size: $('st-size'),
  encode: $('st-encode'),
  clock: $('st-clock'),
  wake: $('st-wake'),
  batt: $('st-batt'),
  btnCsv: $('btn-csv'),
  csvRows: $('csv-rows'),
  btnDemo: $('btn-demo'),
  summary: $('summary'),
  sumConn: $('sum-conn'),
  sumFps: $('sum-fps'),
  sumBatt: $('sum-batt'),
};

const RECONNECT_MAX_MS = 5000;
const FPS_WINDOW_MS = 1000;
const ACK_SAMPLES = 100; // ack 왕복 p50/p95 계산에 쓰는 최근 개수
const ENCODE_SAMPLES = 30; // 인코딩 시간 평균에 쓰는 최근 개수
// ack가 이 시간 안에 안 오면 자리를 비운다(M-25). gateway는 형식이 틀린 프레임에 ack를 보내지 않고,
// publish 오류면 연결을 닫는다(재연결 때 대기 목록을 비움). 정상 ack는 LAN에서 수십 ms라 넉넉히 잡았다.
const ACK_TIMEOUT_MS = 3000;
const LOG_INTERVAL_MS = 1000; // 측정 기록 간격
const LOG_MAX_ROWS = 3600; // 1시간치. 넘으면 오래된 줄부터 버린다(메모리 제한)
const FACING_KEY = 'airstroke.mobile.facing'; // 마지막 카메라 방향(localStorage)
const DEMO_KEY = 'airstroke.mobile.demo'; // 시연 모드 켜짐 여부(localStorage)
const BATTERY_LOW = 0.2; // 이 아래면 경고색
const CLOSE_UNKNOWN_SESSION = 4404; // 모르는(만료된) 세션
const CLOSE_REPLACED = 4409; // 같은 세션에 새 폰이 접속해 밀려남

const state = {
  sid: new URLSearchParams(location.search).get('s'),
  config: null,
  ws: null,
  reconnectMs: 500,
  stream: null,
  facing: loadFacing(), // 'user'(전면) | 'environment'(후면)
  mirror: true,
  camSize: [0, 0], // 실제로 열린 카메라 해상도
  running: false,
  paused: false, // 탭이 백그라운드라 잠시 멈춤(돌아오면 재개)
  timer: null,
  nextTick: 0,
  seq: 0,
  inflight: new Map(), // seq -> 보낸 시각(ms), ack 받으면 삭제
  sent: 0,
  dropped: 0,
  ackTimeouts: 0,
  sendLog: [], // 최근 FPS_WINDOW_MS 안에 보낸 프레임 {t, bytes}
  ackRtts: [],
  encodeMs: [],
  clock: null, // 마지막 clock 메시지 {offset_ms, rtt_ms}
  wakeLock: null,
  battery: null, // BatteryManager(지원 시)
  log: [], // 측정 기록(1초 단위)
  logStart: 0,
  logLast: { sent: 0, dropped: 0, ackTimeouts: 0 },
};

// ---------- 카메라 방향 기억 (M-14) ----------
// 사파리 사생활 보호 모드 등에서는 localStorage가 예외를 던지므로 실패해도 기본값으로 동작한다.

function loadFacing() {
  try {
    const v = localStorage.getItem(FACING_KEY);
    return v === 'environment' ? 'environment' : 'user';
  } catch {
    return 'user';
  }
}

function saveSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* 저장 못 해도 동작에는 지장 없음 */
  }
}

function loadDemo() {
  try {
    return localStorage.getItem(DEMO_KEY) === '1';
  } catch {
    return false;
  }
}

// ---------- 통계 ----------

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

const mean = (values) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);

function pushLimited(arr, value, limit) {
  arr.push(value);
  if (arr.length > limit) arr.shift();
}

/** 지금 시점의 통계 한 묶음. 화면 표시와 측정 기록이 같이 쓴다 */
function snapshot() {
  const now = performance.now();
  while (state.sendLog.length && now - state.sendLog[0].t > FPS_WINDOW_MS) state.sendLog.shift();
  const bytes = state.sendLog.reduce((a, f) => a + f.bytes, 0);
  const n = state.sendLog.length;
  return {
    fps: (n * 1000) / FPS_WINDOW_MS,
    kbPerFrame: n ? bytes / n / 1024 : null,
    kbps: (bytes / 1024) * (1000 / FPS_WINDOW_MS),
    encodeMs: mean(state.encodeMs),
    ackP50: percentile(state.ackRtts, 50),
    ackP95: percentile(state.ackRtts, 95),
  };
}

// ---------- 화면 표시 ----------

function showNotice(text) {
  els.notice.textContent = text;
  els.notice.hidden = !text;
}

function setConn(text, cls) {
  for (const el of [els.conn, els.sumConn]) {
    el.textContent = text;
    el.className = cls;
  }
}

function renderStats() {
  const s = snapshot();
  els.fps.textContent = s.fps.toFixed(1);
  els.sumFps.textContent = `${s.fps.toFixed(1)} fps`;
  els.sent.textContent = state.sent;
  els.drop.textContent = state.ackTimeouts
    ? `${state.dropped} (ack 없음 ${state.ackTimeouts})`
    : state.dropped;
  els.inflight.textContent = state.config
    ? `${state.inflight.size} / ${state.config.max_inflight_frames}`
    : state.inflight.size;
  if (s.ackP50 !== null) els.ack.textContent = `${s.ackP50.toFixed(0)} / ${s.ackP95.toFixed(0)} ms`;
  if (s.kbPerFrame !== null) {
    els.size.textContent = `${s.kbPerFrame.toFixed(1)} KB / ${s.kbps.toFixed(0)} KB/s`;
  }
  if (s.encodeMs !== null) els.encode.textContent = `${s.encodeMs.toFixed(0)} ms`;
}
setInterval(renderStats, 250);

// ---------- 측정 기록 (M-45) ----------

const LOG_COLUMNS = [
  'time',
  'elapsed_s',
  'conn',
  'state',
  'camera',
  'cam_w',
  'cam_h',
  'enc_w',
  'enc_h',
  'send_fps',
  'sent',
  'dropped',
  'ack_timeouts',
  'inflight',
  'kb_per_frame',
  'kb_per_s',
  'encode_ms',
  'ack_p50_ms',
  'ack_p95_ms',
  'clock_offset_ms',
  'clock_rtt_ms',
  'battery_pct',
  'charging',
];

function logTick() {
  if (!state.running && !state.paused) return;
  const s = snapshot();
  const [encW, encH] = els.video.videoWidth ? encodeSize() : [0, 0];
  const round = (v, d = 1) => (v === null || v === undefined ? '' : Number(v.toFixed(d)));
  const row = {
    time: new Date().toISOString(),
    elapsed_s: state.log.length ? round((Date.now() - state.logStart) / 1000) : 0,
    conn: state.ws?.readyState === WebSocket.OPEN ? 'open' : 'closed',
    state: state.paused ? 'paused' : 'running',
    camera: state.mirror ? 'front' : 'back',
    cam_w: state.camSize[0],
    cam_h: state.camSize[1],
    enc_w: encW,
    enc_h: encH,
    send_fps: round(s.fps),
    // 보냄·버림·ack 없음은 직전 기록 이후 늘어난 수(1초 동안의 개수)
    sent: state.sent - state.logLast.sent,
    dropped: state.dropped - state.logLast.dropped,
    ack_timeouts: state.ackTimeouts - state.logLast.ackTimeouts,
    inflight: state.inflight.size,
    kb_per_frame: round(s.kbPerFrame),
    kb_per_s: round(s.kbps),
    encode_ms: round(s.encodeMs),
    ack_p50_ms: round(s.ackP50),
    ack_p95_ms: round(s.ackP95),
    clock_offset_ms: round(state.clock?.offset_ms, 0),
    clock_rtt_ms: round(state.clock?.rtt_ms, 0),
    battery_pct: state.battery ? Math.round(state.battery.level * 100) : '',
    charging: state.battery ? Number(state.battery.charging) : '',
  };
  if (!state.log.length) state.logStart = Date.now();
  state.logLast = { sent: state.sent, dropped: state.dropped, ackTimeouts: state.ackTimeouts };
  pushLimited(state.log, row, LOG_MAX_ROWS);
  els.csvRows.textContent = `${state.log.length}초`;
  els.btnCsv.disabled = false;
}
setInterval(logTick, LOG_INTERVAL_MS);

function csvCell(v) {
  const s = String(v ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv() {
  const cam = state.config?.camera ?? {};
  // 맨 위 '#' 줄: 어떤 기기·설정으로 잰 것인지(시험 조합 구분용)
  const meta = [
    `# user_agent: ${navigator.userAgent}`,
    `# screen: ${screen.width}x${screen.height} @${window.devicePixelRatio}`,
    `# connection: ${navigator.connection?.effectiveType ?? '-'}`,
    `# session: ${state.sid}`,
    `# config: ${cam.width}x${cam.height} ${cam.fps}fps q${cam.jpeg_quality} ` +
      `max_inflight=${state.config?.max_inflight_frames}`,
  ];
  const lines = [
    ...meta,
    LOG_COLUMNS.join(','),
    ...state.log.map((r) => LOG_COLUMNS.map((c) => csvCell(r[c])).join(',')),
  ];
  const blob = new Blob([`${lines.join('\n')}\n`], { type: 'text/csv' });
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `airstroke-mobile-${stamp}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------- 설정 ----------

async function loadConfig() {
  for (;;) {
    try {
      const res = await fetch('/api/config', { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.config = await res.json();
      return;
    } catch (err) {
      showNotice(`설정(/api/config)을 받지 못했습니다: ${err.message}\n2초 뒤 다시 시도합니다.`);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

// ---------- WebSocket ----------

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/mobile/${encodeURIComponent(state.sid)}`);
  ws.binaryType = 'arraybuffer';
  state.ws = ws;
  setConn('연결 중…', 'warn');

  ws.onopen = () => {
    state.reconnectMs = 500;
    state.inflight.clear();
    setConn('연결됨', 'ok');
  };

  ws.onmessage = (ev) => {
    if (typeof ev.data !== 'string') return;
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (msg.type === 'ping') {
      // 시계 동기화: 지연을 줄이려고 다른 처리보다 먼저 즉시 답한다
      ws.send(JSON.stringify({ type: 'pong', id: msg.id, t_server: msg.t_server, t_client: Date.now() }));
    } else if (msg.type === 'ack') {
      const sentAt = state.inflight.get(msg.seq);
      if (sentAt !== undefined) {
        state.inflight.delete(msg.seq);
        pushLimited(state.ackRtts, performance.now() - sentAt, ACK_SAMPLES);
      }
    } else if (msg.type === 'clock') {
      state.clock = msg;
      els.clock.textContent = `${msg.offset_ms.toFixed(0)} / ${msg.rtt_ms.toFixed(0)} ms`;
    }
  };

  ws.onclose = (ev) => {
    if (state.ws !== ws) return;
    state.inflight.clear();
    // gateway가 정한 종료 코드(docs/03-protocol.md): 재접속해도 소용없거나 해로운 경우
    if (ev.code === CLOSE_UNKNOWN_SESSION || ev.code === CLOSE_REPLACED) {
      stopCapture();
      state.paused = false;
      els.btnStart.disabled = true;
      setConn(ev.code === CLOSE_REPLACED ? '다른 폰이 연결됨' : '세션 없음', 'bad');
      showNotice(
        ev.code === CLOSE_REPLACED
          ? '같은 세션에 다른 폰이 접속해서 연결이 끊겼습니다.\n다시 쓰려면 이 페이지를 새로고침하세요.'
          : '세션이 없거나 만료되었습니다.\nPC 그림판에서 새 QR 코드를 스캔하세요.',
      );
      return;
    }
    setConn(`끊김 — ${(state.reconnectMs / 1000).toFixed(1)}초 뒤 재연결`, 'bad');
    setTimeout(connect, state.reconnectMs);
    state.reconnectMs = Math.min(state.reconnectMs * 2, RECONNECT_MAX_MS);
  };
}

// ---------- 카메라 ----------

async function openCamera() {
  const cam = state.config.camera;
  if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
  state.stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: state.facing },
      width: { ideal: cam.width },
      height: { ideal: cam.height },
      frameRate: { ideal: cam.fps },
    },
  });
  const track = state.stream.getVideoTracks()[0];
  const settings = track.getSettings();
  // 실제로 열린 카메라 방향을 우선 사용(PC 웹캠 등은 facingMode가 없을 수 있음)
  const facing = settings.facingMode || state.facing;
  state.mirror = facing === 'user';
  state.camSize = [settings.width ?? 0, settings.height ?? 0];
  els.video.srcObject = state.stream;
  els.video.classList.toggle('mirror', state.mirror);
  await els.video.play();
  els.cam.textContent =
    `${state.mirror ? '전면' : '후면'} ${settings.width ?? '?'}x${settings.height ?? '?'}` +
    (settings.frameRate ? ` @${Math.round(settings.frameRate)}` : '');
}

/** getUserMedia 오류를 사용자가 할 일로 바꿔 안내한다 (M-13) */
function cameraErrorText(err) {
  switch (err.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return (
        '카메라 권한이 거부되었습니다.\n' +
        '주소창의 자물쇠(또는 사이트 설정)에서 카메라를 "허용"으로 바꾼 뒤 새로고침하세요.'
      );
    case 'NotFoundError':
    case 'OverconstrainedError':
      return '사용할 수 있는 카메라를 찾지 못했습니다.\n전면/후면 전환을 눌러 다른 카메라로 시도하세요.';
    case 'NotReadableError':
    case 'AbortError':
      return (
        '다른 앱이 카메라를 쓰고 있습니다.\n' +
        '카메라·영상통화 앱(줌 등)을 닫고 다시 "카메라 시작"을 누르세요.'
      );
    default:
      return `카메라를 열 수 없습니다: ${err.name}\n${err.message ?? ''}`;
  }
}

/** 영상 비율을 유지하면서 설정 해상도(긴 변·짧은 변) 안에 맞춘 인코딩 크기 */
function encodeSize() {
  const vw = els.video.videoWidth;
  const vh = els.video.videoHeight;
  const { width, height } = state.config.camera;
  const longSide = Math.max(width, height);
  const shortSide = Math.min(width, height);
  const [maxW, maxH] = vw >= vh ? [longSide, shortSide] : [shortSide, longSide];
  const scale = Math.min(1, maxW / vw, maxH / vh);
  return [Math.round(vw * scale), Math.round(vh * scale)];
}

// ---------- 프레임 송신 ----------

function encodeFrame(header, jpegBlob) {
  return jpegBlob.arrayBuffer().then((jpeg) => {
    const headerBytes = new TextEncoder().encode(JSON.stringify(header));
    const buf = new Uint8Array(4 + headerBytes.length + jpeg.byteLength);
    new DataView(buf.buffer).setUint32(0, headerBytes.length, false); // big-endian
    buf.set(headerBytes, 4);
    buf.set(new Uint8Array(jpeg), 4 + headerBytes.length);
    return buf.buffer;
  });
}

function captureFrame() {
  const ws = state.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN || !els.video.videoWidth) return;

  // ack가 너무 오래 안 온 프레임은 자리를 비운다(M-25). 안 그러면 송신이 영원히 멈춘다
  const now = performance.now();
  for (const [s, t] of state.inflight) {
    if (now - t > ACK_TIMEOUT_MS) {
      state.inflight.delete(s);
      state.ackTimeouts += 1;
    }
  }

  // 흐름 제어: ack 대기가 꽉 차면 이번 프레임은 버린다
  if (state.inflight.size >= state.config.max_inflight_frames) {
    state.dropped += 1;
    return;
  }

  const captureTs = Date.now();
  const seq = state.seq++;
  const [w, h] = encodeSize();
  const canvas = els.encoder;
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  canvas.getContext('2d').drawImage(els.video, 0, 0, w, h);

  // 인코딩 중인 프레임도 자리를 차지하게 해 동시에 max_inflight_frames 장을 넘지 않게 한다
  state.inflight.set(seq, now);
  canvas.toBlob(
    async (blob) => {
      if (!blob || ws.readyState !== WebSocket.OPEN) {
        state.inflight.delete(seq);
        return;
      }
      // 인코딩 시간 = 캡처(drawImage 직전) → toBlob 완료 (M-43, 저사양 폰 병목 확인)
      pushLimited(state.encodeMs, performance.now() - now, ENCODE_SAMPLES);
      const frame = await encodeFrame({ seq, capture_ts: captureTs, mirror: state.mirror }, blob);
      if (ws.readyState !== WebSocket.OPEN) {
        state.inflight.delete(seq);
        return;
      }
      ws.send(frame);
      state.inflight.set(seq, performance.now()); // ack 왕복은 실제 송신 시점부터 잰다
      state.sent += 1;
      state.sendLog.push({ t: performance.now(), bytes: frame.byteLength });
    },
    'image/jpeg',
    state.config.camera.jpeg_quality / 100,
  );
}

function loop() {
  if (!state.running) return;
  captureFrame();
  // 드리프트 없이 목표 fps를 유지하도록 다음 시각을 누적해서 잡는다
  const interval = 1000 / state.config.camera.fps;
  state.nextTick += interval;
  const now = performance.now();
  if (state.nextTick < now) state.nextTick = now + interval;
  state.timer = setTimeout(loop, state.nextTick - now);
}

// ---------- 화면 꺼짐 방지 ----------

async function requestWakeLock() {
  if (!('wakeLock' in navigator)) {
    els.wake.textContent = '미지원';
    return;
  }
  try {
    state.wakeLock = await navigator.wakeLock.request('screen');
    els.wake.textContent = '켜짐';
    els.wake.className = 'ok';
    state.wakeLock.addEventListener('release', () => {
      els.wake.textContent = '꺼짐';
      els.wake.className = 'warn';
    });
  } catch (err) {
    els.wake.textContent = `실패 (${err.name})`;
    els.wake.className = 'warn';
  }
}

// ---------- 배터리 (M-47) ----------
// Battery Status API는 크롬 계열(안드로이드)만 지원. 사파리·파이어폭스는 '미지원'으로 둔다.

function renderBattery() {
  const b = state.battery;
  const text = `${Math.round(b.level * 100)}%${b.charging ? ' 충전 중' : ''}`;
  const cls = !b.charging && b.level < BATTERY_LOW ? 'warn' : '';
  els.batt.textContent = text;
  els.batt.className = cls;
  els.sumBatt.textContent = `배터리 ${text}`;
  els.sumBatt.className = cls;
}

async function initBattery() {
  if (!navigator.getBattery) {
    els.batt.textContent = '미지원';
    return;
  }
  try {
    state.battery = await navigator.getBattery();
  } catch {
    els.batt.textContent = '미지원';
    return;
  }
  renderBattery();
  state.battery.addEventListener('levelchange', renderBattery);
  state.battery.addEventListener('chargingchange', renderBattery);
}

// ---------- 시연 모드 (M-46) ----------

function setDemo(on) {
  document.body.classList.toggle('demo', on);
  els.summary.hidden = !on;
  els.btnDemo.setAttribute('aria-pressed', String(on));
  els.btnDemo.textContent = on ? '통계 보기' : '시연 모드';
  saveSetting(DEMO_KEY, on ? '1' : '0');
}

// ---------- 시작·중지 ----------

async function startCapture() {
  try {
    await openCamera();
  } catch (err) {
    showNotice(cameraErrorText(err));
    return false;
  }
  showNotice('');
  state.running = true;
  state.paused = false;
  state.nextTick = performance.now();
  loop();
  requestWakeLock();
  els.btnStart.textContent = '중지';
  els.btnStart.classList.add('secondary');
  els.btnFlip.disabled = false;
  return true;
}

function stopCapture() {
  state.running = false;
  clearTimeout(state.timer);
  state.stream?.getTracks().forEach((t) => t.stop());
  state.stream = null;
  state.wakeLock?.release();
  els.btnStart.textContent = '카메라 시작';
  els.btnStart.classList.remove('secondary');
  els.btnFlip.disabled = true;
  els.cam.textContent = '-';
}

// 백그라운드 탭 처리 (M-26): 숨겨지면 카메라를 끄고(브라우저가 어차피 멈추거나 검은 화면을 줌),
// 돌아오면 같은 방향으로 다시 연다. 다시 열면 wake lock도 다시 요청된다.
document.addEventListener('visibilitychange', async () => {
  if (document.visibilityState === 'hidden') {
    if (state.running) {
      stopCapture();
      state.paused = true;
      els.cam.textContent = '일시정지(백그라운드)';
    }
  } else if (state.paused) {
    if (!(await startCapture())) state.paused = false;
  }
});

// ---------- 버튼 ----------

els.btnStart.addEventListener('click', async () => {
  if (state.running) {
    stopCapture();
    return;
  }
  await startCapture();
});

els.btnFlip.addEventListener('click', async () => {
  const prev = state.facing;
  state.facing = prev === 'user' ? 'environment' : 'user';
  els.btnFlip.disabled = true;
  try {
    await openCamera();
    saveSetting(FACING_KEY, state.facing);
    showNotice('');
  } catch (err) {
    state.facing = prev;
    showNotice(cameraErrorText(err));
    await openCamera().catch(() => {});
  } finally {
    els.btnFlip.disabled = !state.running;
  }
});

els.btnCsv.addEventListener('click', downloadCsv);
els.btnDemo.addEventListener('click', () => setDemo(!document.body.classList.contains('demo')));

// ---------- 시작 ----------

async function main() {
  els.sid.textContent = state.sid || '-';
  setDemo(loadDemo());
  initBattery();
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    showNotice('HTTPS가 아니라서 카메라를 쓸 수 없습니다.\nhttps:// 주소로 접속하세요(PC 그림판의 QR 사용).');
    els.btnStart.disabled = true;
    return;
  }
  if (!state.sid) {
    showNotice('세션이 없습니다.\nPC 그림판의 QR 코드를 스캔해서 접속하세요.');
    els.btnStart.disabled = true;
    return;
  }
  els.btnStart.disabled = true;
  await loadConfig();
  showNotice('');
  els.btnStart.disabled = false;
  connect();
}

main();
