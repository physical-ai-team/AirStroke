// AirStroke 그림판 PiP: 폰 카메라 영상(gateway → PC 바이너리, D-015)을 그림판 모서리 패널에 보여준다.
// Zoom 화면 공유로 시청자가 실제 손동작을 볼 수 있게 하는 선택 기능이다.
// 기본 꺼짐. 켜면 {"type":"pip","enabled":true} 를 보내고, 꺼져 있으면 gateway 가 영상을 보내지 않는다.

const CORNERS = ['br', 'bl', 'tl', 'tr']; // 이동 버튼을 누를 때마다 이 순서로 돈다
const ARROWS = { br: '↘', bl: '↙', tl: '↖', tr: '↗' };
const STALE_MS = 2000; // 이 시간 동안 프레임이 없으면 "영상 없음"
const CORNER_KEY = 'airstroke.pip.corner'; // 위치만 기억 (켜짐 상태는 매번 꺼짐으로 시작)

// [4B big-endian 헤더 길이 N][N B UTF-8 JSON 헤더][JPEG] → {header, jpeg}, 형식이 틀리면 null
export function parseFrame(buf) {
  if (!(buf instanceof ArrayBuffer) || buf.byteLength < 4) return null;
  const n = new DataView(buf).getUint32(0);
  if (4 + n > buf.byteLength) return null;
  let header;
  try {
    header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
  } catch {
    return null;
  }
  if (!header || typeof header !== 'object') return null;
  return { header, jpeg: new Blob([new Uint8Array(buf, 4 + n)], { type: 'image/jpeg' }) };
}

function loadCorner() {
  try {
    const c = localStorage.getItem(CORNER_KEY);
    if (CORNERS.includes(c)) return c;
  } catch { /* 저장소 막힘 → 기본 위치 */ }
  return CORNERS[0];
}

function saveCorner(c) {
  try { localStorage.setItem(CORNER_KEY, c); } catch { /* 무시 */ }
}

// 툴바에 켜기/끄기 버튼, stage 에 패널을 만든다.
// app.js 는 연결될 때마다 attach(ws), 바이너리 메시지는 onFrame(buf) 로 넘긴다.
export function createPip({ stage, toolbar }) {
  let enabled = false, ws = null, corner = loadCorner();
  let gen = 0; // 켜기/끄기마다 증가 → 그 전에 디코드하던 프레임은 버린다
  let pending = null, decoding = false, lastFrameAt = 0;

  const toggle = document.createElement('button');
  toggle.id = 'pipToggle';
  toggle.title = '폰 카메라 영상 (켜면 PC로 영상이 전송되어 부하가 늘어남)';
  toolbar.append(toggle);

  const panel = document.createElement('div');
  panel.id = 'pip';
  const view = document.createElement('canvas');
  const vctx = view.getContext('2d');
  const empty = document.createElement('div');
  empty.className = 'pip-empty';
  empty.textContent = '영상 없음';
  const move = document.createElement('button');
  move.className = 'pip-move';
  move.title = '다른 모서리로 옮기기';
  panel.append(view, empty, move);
  stage.append(panel);

  function send() {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'pip', enabled }));
  }

  function render() {
    toggle.textContent = enabled ? '📷 PiP 끄기' : '📷 PiP 켜기';
    toggle.classList.toggle('on', enabled);
    panel.hidden = !enabled;
    panel.className = corner;
    move.textContent = ARROWS[CORNERS[(CORNERS.indexOf(corner) + 1) % CORNERS.length]];
  }

  toggle.onclick = () => {
    enabled = !enabled;
    gen++;
    pending = null;
    lastFrameAt = Date.now(); // "영상 없음"은 켠 뒤 STALE_MS 동안 프레임이 없을 때만
    vctx.clearRect(0, 0, view.width, view.height); // 다시 켤 때 옛 화면이 보이지 않게
    empty.hidden = true;
    send();
    render();
  };

  move.onclick = () => {
    corner = CORNERS[(CORNERS.indexOf(corner) + 1) % CORNERS.length];
    saveCorner(corner);
    render();
  };

  function draw(bmp, mirror) {
    if (view.width !== bmp.width || view.height !== bmp.height) {
      view.width = bmp.width;
      view.height = bmp.height;
      panel.style.aspectRatio = `${bmp.width} / ${bmp.height}`; // 세로 프레임도 비율 유지
    }
    vctx.setTransform(mirror ? -1 : 1, 0, 0, 1, mirror ? view.width : 0, 0);
    vctx.drawImage(bmp, 0, 0);
    vctx.setTransform(1, 0, 0, 1, 0, 0);
  }

  // 디코드 중에 온 프레임은 최신 1장만 남긴다 (Zoom 과 같은 노트북이라 부하를 줄임)
  async function pump() {
    decoding = true;
    try {
      while (pending) {
        const { header, jpeg } = pending, myGen = gen;
        pending = null;
        let bmp;
        try { bmp = await createImageBitmap(jpeg); } catch { continue; }
        try {
          if (myGen === gen && enabled) {
            draw(bmp, header.mirror === true);
            lastFrameAt = Date.now();
            empty.hidden = true;
          }
        } finally {
          bmp.close();
        }
      }
    } finally {
      decoding = false; // 예외가 나도 다음 프레임부터 다시 그린다
    }
  }

  setInterval(() => {
    if (enabled && Date.now() - lastFrameAt > STALE_MS) empty.hidden = false;
  }, 500);

  render();

  return {
    // 새 연결마다 호출. gateway 는 연결 직후 PiP 를 꺼짐으로 두므로 켜져 있으면 다시 알린다
    attach(sock) {
      ws = sock;
      ws.binaryType = 'arraybuffer';
      if (enabled) send();
    },
    onFrame(buf) {
      if (!enabled) return; // 끈 직후 이미 오던 프레임
      const f = parseFrame(buf);
      if (!f) return;
      pending = f;
      if (!decoding) pump();
    },
  };
}
