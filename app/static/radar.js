// レーダー画面。スマホの位置は、この端末の中で計算するだけで、サーバーには一切送らない。
(function () {
  const M = window.RadarMath;
  const asset = JSON.parse(document.getElementById("radar-data").textContent);
  const canvas = document.getElementById("radar");
  const ctx = canvas.getContext("2d");
  const msg = document.getElementById("msg");
  const sub = document.getElementById("sub");
  const compassBtn = document.getElementById("compass-btn");

  let me = null;       // {lat, lon, accuracy}
  let heading = null;  // スマホの向き（北が0、時計回り）。取れないときは null

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
  const size = Math.min(window.innerWidth - 32, 360);
  const dpr = window.devicePixelRatio || 1;
  canvas.width = size * dpr; canvas.height = size * dpr;
  canvas.style.width = size + "px"; canvas.style.height = size + "px";
  ctx.scale(dpr, dpr);

  function draw(j) {
    const c = size / 2, R = c - 24;
    ctx.clearRect(0, 0, size, size);
    ctx.strokeStyle = css("--line"); ctx.fillStyle = css("--muted"); ctx.lineWidth = 1;
    ctx.font = "12px system-ui, sans-serif"; ctx.textAlign = "left";

    const scale = j && j.state !== "unknown" ? M.scaleFor(Math.max(j.distance, j.uncertainty)) : 50;
    for (let i = 1; i <= 3; i++) {                       // 同心円（目盛り）
      ctx.beginPath(); ctx.arc(c, c, (R * i) / 3, 0, Math.PI * 2); ctx.stroke();
      ctx.fillText(Math.round((scale * i) / 3) + "m", c + 4, c - (R * i) / 3 + 12);
    }
    ctx.beginPath(); ctx.moveTo(c, c - R); ctx.lineTo(c, c + R); ctx.moveTo(c - R, c); ctx.lineTo(c + R, c); ctx.stroke();

    // 北の印（スマホの向きが取れているときは、向きに合わせて回す）
    const northAngle = heading == null ? 0 : -heading;
    const nx = c + (R + 12) * Math.sin((northAngle * Math.PI) / 180);
    const ny = c - (R + 12) * Math.cos((northAngle * Math.PI) / 180);
    ctx.fillStyle = css("--err"); ctx.textAlign = "center"; ctx.font = "bold 14px system-ui, sans-serif";
    ctx.fillText("北", nx, ny + 5);

    ctx.fillStyle = css("--accent");                      // 自分（中心）
    ctx.beginPath(); ctx.arc(c, c, 6, 0, Math.PI * 2); ctx.fill();

    if (!j || j.state === "unknown") return;
    const angle = j.bearing - (heading == null ? 0 : heading);
    const r = Math.min((j.distance / scale) * R, R);
    const x = c + r * Math.sin((angle * Math.PI) / 180);
    const y = c - r * Math.cos((angle * Math.PI) / 180);
    const ur = Math.min((j.uncertainty / scale) * R, R);
    ctx.fillStyle = css("--ok"); ctx.globalAlpha = 0.18;   // 誤差の範囲（備品の位置は、この中のどこか）
    ctx.beginPath(); ctx.arc(x, y, ur, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1;
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill();
  }

  // 詳細（数値）：方角が合わないときに、実際の位置関係と見比べるための表示（この端末の画面だけ）
  function showDebug(j) {
    const f = (v, n) => (v == null ? "なし" : v.toFixed(n));
    const lines = [
      "現在地　　：緯度 " + f(me.lat, 6) + " ／ 経度 " + f(me.lon, 6) + " ／ 誤差 " + f(me.accuracy, 0) + "m",
      "備品の位置：緯度 " + f(asset.lat, 6) + " ／ 経度 " + f(asset.lon, 6) + " ／ 誤差 " + f(asset.accuracy, 0) + "m",
      "最後の記録：" + (asset.seen || "なし"),
    ];
    if (j && j.state !== "unknown") {
      lines.push("距離　　　：" + f(j.distance, 1) + "m（誤差の合成 約" + f(j.uncertainty, 0) + "m）");
      lines.push("備品の方位：" + f(j.bearing, 0) + "°（" + M.compassName(j.bearing) + "。北が0°、時計回り）");
    }
    lines.push("スマホの向き：" + (heading == null ? "未使用（北が上の表示）" : f(heading, 0) + "°（" + M.compassName(heading) + "）"));
    document.getElementById("debug").textContent = lines.join("\n");
  }

  function update() {
    if (!me) return;
    const j = M.judge(me, asset);
    showDebug(j);
    if (j.state === "unknown") {
      msg.textContent = "この備品は、位置が記録されていません。";
      sub.textContent = "備品タグにタッチすると、位置が記録されます。";
      draw(j); return;
    }
    const where = heading == null
      ? M.compassName(j.bearing) + "の方向"
      : M.relativeName(j.bearing - heading) + "（" + M.compassName(j.bearing) + "）の方向";
    if (j.state === "within") {
      msg.textContent = "近くにいます（距離が誤差の範囲内）";
      sub.textContent = "位置の誤差が約" + Math.round(j.uncertainty) + "mあるため、方向は分かりません。周りを探してください。";
    } else {
      msg.textContent = M.formatDistance(j.distance) + "、" + where;
      sub.textContent = "位置の誤差が約" + Math.round(j.uncertainty) + "mあるため、おおよその目安です。";
    }
    draw(j);
  }

  // スマホの位置：この画面を開いている間だけ連続で取得する（サーバーには送らない）
  let watchId = null;
  function start() {
    if (!("geolocation" in navigator)) { msg.textContent = "この端末は位置情報に対応していません。"; return; }
    msg.textContent = "現在地を取得しています…";
    watchId = navigator.geolocation.watchPosition(
      (pos) => { me = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy }; update(); },
      (err) => {
        msg.textContent = err.code === 1
          ? "位置情報が許可されていません。設定で、このサイトの位置情報を許可してください。"
          : "現在地を取得できません。";
      },
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 }
    );
  }
  function stop() { if (watchId != null) { navigator.geolocation.clearWatch(watchId); watchId = null; } }
  window.addEventListener("pagehide", stop);
  document.addEventListener("visibilitychange", () => { document.hidden ? stop() : (watchId == null && start()); });

  // 向き：iPhone は、ボタンを押して許可を得る必要がある
  function onOrientation(e) {
    if (typeof e.webkitCompassHeading === "number") heading = e.webkitCompassHeading;       // iPhone
    else if (e.absolute && typeof e.alpha === "number") heading = (360 - e.alpha) % 360;     // Android
    update();
  }
  function listenOrientation() {
    window.addEventListener("deviceorientationabsolute", onOrientation, true);
    window.addEventListener("deviceorientation", onOrientation, true);
    compassBtn.style.display = "none";
  }
  if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
    compassBtn.style.display = "";
    compassBtn.addEventListener("click", async () => {
      try { if ((await DeviceOrientationEvent.requestPermission()) === "granted") listenOrientation(); else sub.textContent = "コンパスが許可されませんでした（北が上の表示になります）。"; }
      catch (e) { sub.textContent = "コンパスを使えません（北が上の表示になります）。"; }
    });
  } else if (typeof DeviceOrientationEvent !== "undefined") {
    compassBtn.style.display = "none"; listenOrientation();
  } else { compassBtn.style.display = "none"; }

  draw(null);
  start();
})();
