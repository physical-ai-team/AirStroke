// 테스트 모드(?mock=1): gateway 없이 CommandMsg 를 만들어 그림판에 넘긴다.
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

export function startMock({ target, button, onCommand }) {
  let seq = 0, strokeId = 0, timer = null, steps = null;

  function emit(gesture, action, cursor, newStroke) {
    if (newStroke) strokeId++;
    const ts = Date.now();
    onCommand({
      ts, seq: seq++, gesture, action, cursor,
      stroke_id: action === 'draw' ? strokeId : null,
      trace: { capture: ts, gw_recv: ts, vision_done: ts, gesture_done: ts },
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

  // 마우스: 왼쪽 드래그 = 그리기, 오른쪽 드래그 = 지우개, 버튼 없이 움직이면 = 이동
  const norm = (e) => {
    const r = target.getBoundingClientRect();
    const clamp = (v) => Math.min(1, Math.max(0, v));
    return { x: clamp((e.clientX - r.left) / r.width), y: clamp((e.clientY - r.top) / r.height) };
  };
  target.addEventListener('contextmenu', (e) => e.preventDefault());
  target.addEventListener('pointerdown', (e) => {
    play(false);
    target.setPointerCapture(e.pointerId);
    if (e.button === 0) emit('index', 'draw', norm(e), true);
    else if (e.button === 2) emit('palm', 'erase', norm(e), false);
  });
  target.addEventListener('pointermove', (e) => {
    if (timer) return;
    if (e.buttons & 1) emit('index', 'draw', norm(e), false);
    else if (e.buttons & 2) emit('palm', 'erase', norm(e), false);
    else emit('index_middle', 'move', norm(e), false);
  });
  target.addEventListener('pointerup', (e) => { if (!timer) emit('index_middle', 'move', norm(e), false); });
  target.addEventListener('pointerleave', () => { if (!timer) emit('none', 'idle', null, false); });

  play(true);
}
