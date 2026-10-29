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
  clock: $('st-clock'),
  wake: $('st-wake'),
};

const RECONNECT_MAX_MS = 5000;
const FPS_WINDOW_MS = 1000;
const ACK_AVG_SAMPLES = 30;

const state = {
  sid: new URLSearchParams(location.search).get('s'),
  config: null,
  ws: null,
  reconnectMs: 500,
  stream: null,
  facing: 'user', // 'user'(전면) | 'environment'(후면)
  mirror: true,
  running: false,
  timer: null,
  nextTick: 0,
  seq: 0,
  inflight: new Map(), // seq -> 보낸 시각(ms), ack 받으면 삭제
  sent: 0,
  dropped: 0,
  sendTimes: [], // 최근 FPS_WINDOW_MS 안에 보낸 시각
  ackRtts: [],
  wakeLock: null,
};

// ---------- 화면 표시 ----------

function showNotice(text) {
  els.notice.textContent = text;
  els.notice.hidden = !text;
}

function setConn(text, cls) {
  els.conn.textContent = text;
  els.conn.className = cls;
}

function renderStats() {
  const now = performance.now();
  while (state.sendTimes.length && now - state.sendTimes[0] > FPS_WINDOW_MS) state.sendTimes.shift();
  els.fps.textContent = ((state.sendTimes.length * 1000) / FPS_WINDOW_MS).toFixed(1);
  els.sent.textContent = state.sent;
  els.drop.textContent = state.dropped;
  els.inflight.textContent = state.config
    ? `${state.inflight.size} / ${state.config.max_inflight_frames}`
    : state.inflight.size;
  if (state.ackRtts.length) {
    const avg = state.ackRtts.reduce((a, b) => a + b, 0) / state.ackRtts.length;
    els.ack.textContent = `${avg.toFixed(0)} ms`;
  }
}
setInterval(renderStats, 250);

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
        state.ackRtts.push(performance.now() - sentAt);
        if (state.ackRtts.length > ACK_AVG_SAMPLES) state.ackRtts.shift();
      }
    } else if (msg.type === 'clock') {
      els.clock.textContent = `${msg.offset_ms.toFixed(0)} / ${msg.rtt_ms.toFixed(0)} ms`;
    }
  };

  ws.onclose = () => {
    if (state.ws !== ws) return;
    state.inflight.clear();
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
  els.video.srcObject = state.stream;
  els.video.classList.toggle('mirror', state.mirror);
  await els.video.play();
  els.cam.textContent =
    `${state.mirror ? '전면' : '후면'} ${settings.width ?? '?'}x${settings.height ?? '?'}` +
    (settings.frameRate ? ` @${Math.round(settings.frameRate)}` : '');
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
  state.inflight.set(seq, performance.now());
  canvas.toBlob(
    async (blob) => {
      if (!blob || ws.readyState !== WebSocket.OPEN) {
        state.inflight.delete(seq);
        return;
      }
      const frame = await encodeFrame({ seq, capture_ts: captureTs, mirror: state.mirror }, blob);
      if (ws.readyState !== WebSocket.OPEN) {
        state.inflight.delete(seq);
        return;
      }
      ws.send(frame);
      state.inflight.set(seq, performance.now()); // ack 왕복은 실제 송신 시점부터 잰다
      state.sent += 1;
      state.sendTimes.push(performance.now());
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

document.addEventListener('visibilitychange', () => {
  // 다른 앱에 다녀오면 wake lock이 풀리므로 다시 요청한다
  if (document.visibilityState === 'visible' && state.running) requestWakeLock();
});

// ---------- 버튼 ----------

els.btnStart.addEventListener('click', async () => {
  if (state.running) {
    state.running = false;
    clearTimeout(state.timer);
    state.stream?.getTracks().forEach((t) => t.stop());
    state.stream = null;
    state.wakeLock?.release();
    els.btnStart.textContent = '카메라 시작';
    els.btnStart.classList.remove('secondary');
    els.btnFlip.disabled = true;
    els.cam.textContent = '-';
    return;
  }
  try {
    await openCamera();
  } catch (err) {
    showNotice(`카메라를 열 수 없습니다: ${err.name}\n브라우저의 카메라 권한을 확인하세요.`);
    return;
  }
  showNotice('');
  state.running = true;
  state.nextTick = performance.now();
  loop();
  requestWakeLock();
  els.btnStart.textContent = '중지';
  els.btnStart.classList.add('secondary');
  els.btnFlip.disabled = false;
});

els.btnFlip.addEventListener('click', async () => {
  const prev = state.facing;
  state.facing = prev === 'user' ? 'environment' : 'user';
  els.btnFlip.disabled = true;
  try {
    await openCamera();
  } catch (err) {
    state.facing = prev;
    showNotice(`카메라 전환 실패: ${err.name}`);
    await openCamera().catch(() => {});
  } finally {
    els.btnFlip.disabled = !state.running;
  }
});

// ---------- 시작 ----------

async function main() {
  els.sid.textContent = state.sid || '-';
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
