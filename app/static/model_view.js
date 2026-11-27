// 3Dモデル（3DGS）の表示と、フロア図との座標合わせ（管理画面）。
// 計算は model_align.js（window.ModelAlign）。モデルは動かさず、備品とアンカーの札を、モデルの座標に置く。
import * as THREE from "three";
import * as GS from "/static/vendor/gaussian-splats-3d.module.js";

const A = window.ModelAlign;
const S = JSON.parse(document.getElementById("state").textContent);
const wrap = document.getElementById("viewer-wrap");
const box = document.getElementById("viewer");
const csrf = wrap.dataset.csrf;
const $ = (id) => document.getElementById(id);

const COLORS = { ok: 0x22c55e, missed: 0xf59e0b, unexpected: 0xd946ef, moved: 0x06b6d4, anchor: 0x38bdf8, pick: 0xffffff };
const STATUS_TEXT = { ok: "通常・確認済み", moved: "場所違い", missed: "未確認", unexpected: "想定外・場所違い" };

let ySign = S.ySign;
let floorY = S.floorY;
let transform = S.transform;           // {s, theta, tx, ty, rms} か null
const pairs = new Map(S.pairs.map((p) => [p.anchor, [p.mx, p.my, p.mz]]));
let pickFor = null;                    // いま、モデル上の位置を指定中のアンカー
let dirty = false;
let bounds = { center: new THREE.Vector3(), radius: 5 };

const overlayScene = new THREE.Scene();
const overlay = new THREE.Group();
overlayScene.add(overlay);

const viewer = new GS.Viewer({
  rootElement: box, cameraUp: [0, ySign, 0], initialCameraPosition: [0, ySign * 6, 6],
  sharedMemoryForWorkers: false, gpuAcceleratedSort: false,
  sceneRevealMode: GS.SceneRevealMode.Instant,  // じわじわ表示（端が欠けて見える）にしない
});

// ビューアは、自分の3Dシーンを先に描き、モデルを後から重ねる。札がモデルの下に隠れないよう、モデルの後に、札を描く。
{
  const baseRender = viewer.render.bind(viewer);
  viewer.render = () => {
    baseRender();
    const r = viewer.renderer, saved = r.autoClear;
    r.autoClear = false;
    r.clearDepth();
    r.render(overlayScene, viewer.camera);
    r.autoClear = saved;
  };
}

const FORMAT = { ".ply": GS.SceneFormat.Ply, ".splat": GS.SceneFormat.Splat, ".ksplat": GS.SceneFormat.KSplat };

// ---- 表示するもの ----
function setStatus(text, kind) {
  const el = $("save-status");
  el.textContent = text;
  el.className = "note" + (kind === "err" ? " err" : "");
}

function labelSprite(text, color, unit) {
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d");
  ctx.font = "bold 44px sans-serif";
  const w = Math.ceil(ctx.measureText(text).width) + 28;
  c.width = w; c.height = 72;
  ctx.font = "bold 44px sans-serif";
  ctx.fillStyle = "rgba(15,23,42,.82)";
  ctx.beginPath(); ctx.roundRect(0, 0, w, 72, 14); ctx.fill();
  ctx.strokeStyle = "#" + color.toString(16).padStart(6, "0"); ctx.lineWidth = 5;
  ctx.beginPath(); ctx.roundRect(2, 2, w - 4, 68, 12); ctx.stroke();
  ctx.fillStyle = "#fff"; ctx.textBaseline = "middle";
  ctx.fillText(text, 14, 38);
  const tex = new THREE.CanvasTexture(c);
  // 拡大・縮小しても、読める大きさ（画面上で一定）にする
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true, sizeAttenuation: false }));
  const h = 0.036;
  sp.scale.set((h * w) / 72, h, 1);
  sp.renderOrder = 1000;
  return sp;
}

function marker(pos, color, unit, label, opts = {}) {
  const g = new THREE.Group();
  const geo = opts.diamond ? new THREE.OctahedronGeometry(0.11 * unit) : new THREE.SphereGeometry(0.11 * unit, 16, 12);
  const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true }));
  m.renderOrder = 999;
  g.add(m);
  if (label) {
    const sp = labelSprite(label, color, unit);
    sp.position.set(0, ySign * (0.3 * unit), 0);
    g.add(sp);
  }
  g.position.fromArray(pos);
  return g;
}

function clearOverlay() {
  while (overlay.children.length) {
    const o = overlay.children.pop();
    o.traverse((n) => { n.geometry?.dispose(); n.material?.map?.dispose(); n.material?.dispose(); });
  }
}

const DEFAULT_H = () => Number($("pin-h").value) || 0;
// 備品の札の高さ：記録された高さがあれば、それ。なければ、画面で決めた高さ
function pinHeight(it) { return it && it.z != null ? it.z : DEFAULT_H(); }

function rebuildOverlay() {
  clearOverlay();
  const names = new Map(S.anchors.map((a) => [a.token, a.name]));
  const baseUnit = bounds.radius / 30;
  if (!transform) {
    // 指定した対応点（座標合わせの前だけ。合わせた後は、アンカーの札が同じ場所に出る）
    for (const [tok, m] of pairs) overlay.add(marker(m, COLORS.pick, baseUnit, names.get(tok) || tok, { diamond: true }));
    return;
  }
  const unit = 1 / transform.s;  // モデルの1 = フロア図の s m。フロア図の1mは、モデルの 1/s
  const toModel = (x, y, h) => A.planToModel(transform, x, y, h, ySign, floorY);
  if ($("show-anchors").checked) {
    for (const a of S.anchors) overlay.add(marker(toModel(a.x, a.y, 0), COLORS.anchor, unit, "⚓ " + a.name, { diamond: true }));
  }
  const filter = $("filter").value;
  for (const it of S.items) {
    if (filter !== "all" && it.status !== filter) continue;
    const col = COLORS[it.status];
    const top = toModel(it.x, it.y, pinHeight(it));
    const label = (it.asset_no ? it.asset_no + " " : "") + it.name + (it.z != null ? ` ${it.z.toFixed(1)}m` : "");
    overlay.add(marker(top, col, unit, label));
    // 床からの線
    const foot = toModel(it.x, it.y, 0);
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...foot), new THREE.Vector3(...top)]),
      new THREE.LineBasicMaterial({ color: col, depthTest: false, transparent: true, opacity: 0.8 }));
    line.renderOrder = 998;
    overlay.add(line);
    // ARの位置のずれ（誤差）の範囲
    if ($("show-err").checked && it.err_m > 0) {
      const r = it.err_m * unit;
      const ring = new THREE.Mesh(new THREE.RingGeometry(Math.max(r - 0.03 * unit, 0), r, 40),
        new THREE.MeshBasicMaterial({ color: col, depthTest: false, transparent: true, opacity: 0.55, side: THREE.DoubleSide }));
      ring.rotation.x = (-ySign * Math.PI) / 2;
      ring.position.set(foot[0], foot[1], foot[2]);
      ring.renderOrder = 997;
      overlay.add(ring);
    }
  }
}

// ---- 備品の一覧 ----
function renderItems() {
  const body = $("items-body");
  body.replaceChildren();
  if (!S.items.length) {
    const tr = body.insertRow(); const td = tr.insertCell(); td.colSpan = 3; td.className = "note";
    td.textContent = "この階に、位置の分かる備品は、まだありません。";
    return;
  }
  for (const it of S.items) {
    const tr = body.insertRow();
    tr.insertCell().textContent = (it.asset_no ? it.asset_no + " " : "") + it.name + (it.z != null ? `（高さ ${it.z.toFixed(1)}m）` : "");
    const st = tr.insertCell(); st.textContent = STATUS_TEXT[it.status]; st.className = "st-" + it.status;
    const go = tr.insertCell();
    const b = document.createElement("button"); b.type = "button"; b.textContent = "ここへ"; b.className = "small";
    b.disabled = !transform;
    b.addEventListener("click", () => {
      const p = A.planToModel(transform, it.x, it.y, pinHeight(it), ySign, floorY);
      const v = new THREE.Vector3(...p);
      const d = v.clone().sub(viewer.controls.target);
      viewer.camera.position.add(d); viewer.controls.target.copy(v); viewer.controls.update();
    });
    go.appendChild(b);
  }
}

// ---- 座標合わせ ----
function refit() {
  const list = [];
  for (const a of S.anchors) {
    const m = pairs.get(a.token);
    if (m) list.push({ anchor: a.token, u: A.groundOf(m, ySign), p: [a.x, a.y] });
  }
  if (list.length < 2) { transform = null; return { list, f: null }; }
  const f = A.fit(list);
  if (f.error) { transform = null; return { list, f }; }
  transform = { s: f.s, theta: f.theta, tx: f.tx, ty: f.ty, rms: f.rms };
  return { list, f };
}

function renderAnchors() {
  const { list, f } = refit();
  const resid = new Map();
  if (f && f.residuals) list.forEach((q, i) => resid.set(q.anchor, f.residuals[i]));
  const body = $("anchors-body");
  body.replaceChildren();
  if (!S.anchors.length) {
    const tr = body.insertRow(); const td = tr.insertCell(); td.colSpan = 4; td.className = "note";
    td.textContent = "この階にアンカーがありません。先に「アンカー」で、フロア図上の位置つきで登録してください。";
  }
  for (const a of S.anchors) {
    const tr = body.insertRow();
    tr.insertCell().textContent = a.name;
    tr.insertCell().textContent = `(${a.x}, ${a.y})`;
    const st = tr.insertCell();
    if (pickFor === a.token) st.textContent = "クリック待ち…";
    else if (pairs.has(a.token)) st.textContent = resid.has(a.token) ? `指定済み（ずれ ${resid.get(a.token).toFixed(2)}m）` : "指定済み";
    else st.textContent = "未指定";
    const act = tr.insertCell();
    const pick = document.createElement("button"); pick.type = "button"; pick.className = "small";
    pick.textContent = pairs.has(a.token) ? "指定し直す" : "モデル上で指定";
    pick.addEventListener("click", () => startPick(a.token));
    act.appendChild(pick);
    if (pairs.has(a.token)) {
      const del = document.createElement("button"); del.type = "button"; del.className = "small secondary"; del.textContent = "消す";
      del.addEventListener("click", () => { pairs.delete(a.token); changed(); });
      act.appendChild(del);
    }
  }
  const res = $("result");
  if (f && f.error) res.textContent = f.error;
  else if (!transform) res.textContent = `対応点を2つ以上（3つ以上を推奨）指定してください。いま ${list.length} 個。`;
  else {
    const deg = ((((transform.theta * 180) / Math.PI) % 360) + 360) % 360;
    res.textContent = `縮尺：モデルの 1 = 実寸 ${transform.s.toFixed(3)}m ／ 回転 ${deg.toFixed(1)}° ／ ずれ（rms）${transform.rms.toFixed(2)}m`
      + (list.length < 3 ? "（2点だけだと、ずれは分かりません。3点以上にしてください）" : "");
  }
  $("pin-controls").hidden = !transform;
}

function changed() {
  dirty = true;
  setStatus("未保存の変更があります。", "");
  pickFor = null;
  $("pick-banner").hidden = true;
  renderAnchors(); renderItems(); rebuildOverlay();
}

function startPick(token) {
  pickFor = token;
  const a = S.anchors.find((x) => x.token === token);
  $("pick-banner").hidden = false;
  $("pick-banner").textContent = `「${a.name}」の位置を、モデルを真上から見て、クリックしてください（柱や壁の根元など、床に接している所）。`;
  topView();
  wrap.scrollIntoView({ block: "start" });  // 一覧のボタンから押したとき、モデルが画面の外にならないように
  renderAnchors();
}

// ---- カメラ ----
function topView() {
  const c = bounds.center, d = bounds.radius * 3.3;  // 部屋の端まで、画面に収める（床は、中心より遠い）
  viewer.camera.position.set(c.x, c.y + ySign * d, c.z + d * 0.02);
  viewer.controls.target.copy(c);
  viewer.controls.update();
}
function sideView() {
  const c = bounds.center, d = bounds.radius * 2.2;
  viewer.camera.position.set(c.x + d * 0.6, c.y + ySign * d * 0.6, c.z + d * 0.8);
  viewer.controls.target.copy(c);
  viewer.controls.update();
}

// 画面のクリック → モデルの床の面の上の点
const raycaster = new THREE.Raycaster();
function floorPointAt(ev) {
  const r = viewer.renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(ndc, viewer.camera);
  const o = raycaster.ray.origin, d = raycaster.ray.direction;
  return A.rayToFloor([o.x, o.y, o.z], [d.x, d.y, d.z], floorY);
}

let down = null;
box.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; });
box.addEventListener("pointerup", (e) => {
  if (!down || !pickFor) return;
  const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
  down = null;
  if (moved > 5) return;  // ドラッグ（視点の操作）は、指定にしない
  const p = floorPointAt(e);
  if (!p) { setStatus("床の面と交わりません。視点を、上から見る向きにしてください。", "err"); return; }
  pairs.set(pickFor, p);
  changed();
});

// ---- 保存 ----
async function save(clear = false) {
  const body = {
    y_sign: ySign, floor_y: floorY,
    pairs: [...pairs].map(([anchor, m]) => ({ anchor, mx: m[0], my: m[1], mz: m[2] })),
    transform: clear || !transform ? null : transform,
  };
  setStatus("保存しています…", "");
  try {
    const r = await fetch(`/admin/models/${S.floor}/align`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body),
    });
    if (!r.ok) { setStatus((await r.json().catch(() => ({}))).detail || "保存できませんでした。", "err"); return false; }
    dirty = false;
    setStatus(transform && !clear ? "保存しました。" : "保存しました（座標は未設定）。", "");
    return true;
  } catch (e) {
    setStatus("通信できませんでした。", "err");
    return false;
  }
}

$("save").addEventListener("click", () => save());
$("reset").addEventListener("click", () => {
  if (!confirm("指定した対応点を、すべて消して、合わせ直します。よろしいですか？")) return;
  pairs.clear(); changed(); save(true);
});
$("view-top").addEventListener("click", topView);
$("view-side").addEventListener("click", sideView);
$("floor-y").addEventListener("change", () => { floorY = Number($("floor-y").value) || 0; if (pairs.size) changed(); else rebuildOverlay(); });
$("y-sign").addEventListener("change", async () => {
  if (!confirm("上下の向きを変えると、対応点は消えて、画面を読み込み直します。よろしいですか？")) { $("y-sign").value = String(ySign); return; }
  ySign = Number($("y-sign").value); pairs.clear(); transform = null;
  if (await save(true)) location.reload();
});
for (const id of ["pin-h", "show-anchors", "show-err", "filter"]) $(id).addEventListener("input", rebuildOverlay);
window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

// ---- 起動 ----
$("floor-y").value = String(floorY);
$("y-sign").value = String(ySign);
$("pin-h").value = "1";
const ext = S.modelUrl.split("?")[0].match(/\.[a-z]+$/)[0];
try {
  await viewer.addSplatScene(S.modelUrl, { format: FORMAT[ext], showLoadingUI: true, progressiveLoad: false });
  viewer.start();
} catch (e) {
  setStatus("モデルを読み込めませんでした：" + (e && e.message ? e.message : e), "err");
  throw e;
}

// モデルの範囲（点を間引いて調べる）と、床の高さの推定
{
  const mesh = viewer.splatMesh, n = mesh.getSplatCount(), step = Math.max(1, Math.floor(n / 20000));
  const v = new THREE.Vector3(), min = new THREE.Vector3(1e30, 1e30, 1e30), max = new THREE.Vector3(-1e30, -1e30, -1e30);
  const ups = [];
  for (let i = 0; i < n; i += step) {
    mesh.getSplatCenter(i, v, false);
    min.min(v); max.max(v); ups.push(ySign * v.y);
  }
  bounds.center.copy(min).add(max).multiplyScalar(0.5);
  bounds.radius = Math.max(0.5, min.distanceTo(max) / 2);
  if (!transform && !pairs.size && !S.floorYSaved) {
    ups.sort((a, b) => a - b);
    floorY = ySign * ups[Math.floor(ups.length * 0.02)];
    $("floor-y").value = floorY.toFixed(3);
  }
}
topView();
renderAnchors(); renderItems(); rebuildOverlay();
setStatus(transform ? "保存済みの座標を使っています。" : "まだ座標を合わせていません。", "");
window.__modelView = { viewer, get transform() { return transform; }, pairs, bounds };  // 動作確認用
