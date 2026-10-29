// 테스트 모드(?mock=1): gateway 없이 CommandMsg·LandmarksMsg 를 만들어 그림판에 넘긴다.
// 시나리오는 tools/mock_commands.py 와 같다(약 13초 반복): 손 없음 → 주먹 → 8자 그리기
// → 펜 들고 이동 → 원 그리기 → 손바닥 지우개 → 주먹. 마우스로 직접 그릴 수도 있다.

const FPS = 15;

// [초, gesture, action, path] — path 가 null 이면 손 없음 (cursor=null)
const PHASES = [
  [1.0, 'none', 'idle', null],
  [1.0, 'fist', 'idle', 'rest'],
  [4.0, 'index', 'draw', 'figure8'],
  [1.0, 'index_middle', 'move', 'to_circle'],
  [3.0, 'index', 'draw', 'circle'],
  [2.0, 'palm', 'erase', 'sweep'],
  [1.0, 'fist', 'idle', 'rest'],
];

// t: 구간 진행률 0~1 → 캔버스 정규화 좌표
function pointOn(path, t) {
  const a = t * 2 * Math.PI;
  switch (path) {
    case 'rest': return { x: 0.5, y: 0.5 };
    case 'figure8': return { x: 0.35 + 0.2 * Math.sin(a), y: 0.5 + 0.2 * Math.sin(a) * Math.cos(a) };
    case 'to_circle': return { x: 0.35 + 0.5 * t, y: 0.5 };
    case 'circle': return { x: 0.7 + 0.15 * Math.cos(a), y: 0.5 + 0.15 * Math.sin(a) };
    case 'sweep': return { x: 0.2 + 0.6 * t, y: 0.5 + 0.1 * Math.sin(t * 6 * Math.PI) };
  }
  throw new Error(path);
}

function* scenario() {
  for (const [seconds, gesture, action, path] of PHASES) {
    const n = Math.max(1, Math.round(seconds * FPS));
    for (let i = 0; i < n; i++) {
      const cursor = path ? pointOn(path, i / Math.max(1, n - 1)) : null;
      yield [gesture, action, cursor, action === 'draw' && i === 0];
    }
  }
}

// ---------- 가짜 손 뼈대 (tools/gen_synthetic_landmarks.py 와 같은 손 모양) ----------
// 손목 기준 MCP(엄지는 CMC) 위치 (손 크기 단위, y는 위쪽이 음수)
const BASES = {
  thumb: [-0.25, -0.15], index: [-0.15, -0.55], middle: [0.0, -0.58],
  ring: [0.12, -0.55], pinky: [0.22, -0.48],
};
const FINGERS = ['thumb', 'index', 'middle', 'ring', 'pinky'];
const POSES = { // 펴진 손가락
  index: ['index'], index_middle: ['index', 'middle'], fist: [], palm: FINGERS,
};
const HAND_SIZE = 0.28; // 캔버스 높이 대비
const FRAME = { width: 640, height: 480 };

function fingerPoints(name, extended) {
  let [x, y] = BASES[name];
  let steps;
  if (name === 'thumb') {
    steps = extended ? [[-0.15, -0.10], [-0.12, -0.08], [-0.10, -0.06]]
      : [[-0.02, -0.12], [0.10, -0.06], [0.10, 0.04]];
  } else {
    const k = name === 'pinky' ? 0.75 : 1;
    steps = extended ? [[0, -0.22 * k], [0, -0.16 * k], [0, -0.13 * k]]
      : [[0, -0.12], [0.01, 0.10], [0, 0.10]];
  }
  const pts = [[x, y]];
  for (const [dx, dy] of steps) { x += dx; y += dy; pts.push([x, y]); }
  return pts;
}

// 검지 끝(8번)이 cursor 에 오도록 손을 만들고, 그림판의 변환(셀카 반전 + 중앙 영역)을
// 거꾸로 적용해 카메라 원본 좌표로 돌려준다 — 실제 landmarks 와 같은 경로를 시험하기 위함
function fakeHand(pose, cursor, activeArea) {
  const rel = [[0, 0]];
  for (const f of FINGERS) rel.push(...fingerPoints(f, POSES[pose].includes(f)));
  const [tipX, tipY] = rel[8];
  const sx = HAND_SIZE * FRAME.height / FRAME.width, sy = HAND_SIZE;
  const m = (1 - activeArea) / 2;
  return rel.map(([dx, dy]) => {
    const cx = cursor.x + (dx - tipX) * sx, cy = cursor.y + (dy - tipY) * sy;
    return [1 - (cx * activeArea + m), cy * activeArea + m, 0]; // mirror=true
  });
}

export function startMock({ target, button, activeArea, onCommand, onLandmarks }) {
  let seq = 0, strokeId = 0, timer = null, steps = null;

  function emit(gesture, action, cursor, newStroke) {
    if (newStroke) strokeId++;
    const ts = Date.now();
    const trace = { capture: ts, gw_recv: ts, vision_done: ts, gesture_done: ts };
    const hands = cursor && POSES[gesture]
      ? [{ handedness: 'Right', score: 0.98, points: fakeHand(gesture, cursor, activeArea) }]
      : [];
    onLandmarks({ ts, seq, mirror: true, ...FRAME, hands, trace });
    onCommand({
      ts, seq: seq++, gesture, action, cursor,
      stroke_id: action === 'draw' ? strokeId : null,
      trace,
    });
  }

  function tick() {
    let step = steps.next();
    if (step.done) { steps = scenario(); step = steps.next(); }
    emit(...step.value);
  }

  function play(on) {
    clearInterval(timer);
    timer = null;
    if (on) { steps = scenario(); timer = setInterval(tick, 1000 / FPS); }
    button.textContent = on ? '■ 시나리오 정지' : '▶ 시나리오 재생';
  }
  button.onclick = () => play(!timer);

  // 마우스: 왼쪽 드래그 = 그리기, 오른쪽 드래그 = 지우개, 가운데 드래그 = 집기(색 선택),
  // 버튼 없이 움직이면 = 이동. 키보드 U = 엄지 세움(실행 취소, 한 번만 보냄)
  const norm = (e) => {
    const r = target.getBoundingClientRect();
    const clamp = (v) => Math.min(1, Math.max(0, v));
    return { x: clamp((e.clientX - r.left) / r.width), y: clamp((e.clientY - r.top) / r.height) };
  };
  target.addEventListener('contextmenu', (e) => e.preventDefault());
  target.addEventListener('mousedown', (e) => { if (e.button === 1) e.preventDefault(); }); // 자동 스크롤 막기
  target.addEventListener('pointerdown', (e) => {
    play(false);
    target.setPointerCapture(e.pointerId);
    if (e.button === 0) emit('index', 'draw', norm(e), true);
    else if (e.button === 2) emit('palm', 'erase', norm(e), false);
    else if (e.button === 1) { e.preventDefault(); emit('pinch', 'select', norm(e), false); }
  });
  target.addEventListener('pointermove', (e) => {
    if (timer) return;
    if (e.buttons & 1) emit('index', 'draw', norm(e), false);
    else if (e.buttons & 2) emit('palm', 'erase', norm(e), false);
    else if (e.buttons & 4) emit('pinch', 'select', norm(e), false);
    else emit('index_middle', 'move', norm(e), false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'u' || e.repeat || e.ctrlKey || e.target.tagName === 'INPUT') return;
    play(false);
    emit('thumb_up', 'undo', { x: 0.5, y: 0.5 }, false);
  });
  document.addEventListener('keyup', (e) => {
    if (e.key === 'u' && !timer) emit('fist', 'idle', { x: 0.5, y: 0.5 }, false);
  });
  target.addEventListener('pointerup', (e) => { if (!timer) emit('index_middle', 'move', norm(e), false); });
  target.addEventListener('pointerleave', () => { if (!timer) emit('none', 'idle', null, false); });

  play(true);
}
