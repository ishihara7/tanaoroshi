// 3Dモデルと、フロア図（階ごとの x=東・y=北、単位m）の座標合わせ。ブラウザでも Node.js（テスト）でも使える。
//
// モデル座標は、Y軸が上（y_sign=1）か、下（y_sign=-1：COLMAPの出力そのまま等）。
// 地面の2D座標 u = (mx, -y_sign*mz)、高さ = y_sign*(my - floor_y)。
// フロア図の座標 p = s * R(theta) * u + t（拡大縮小・回転・平行移動のみ。鏡映はなし）。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ModelAlign = factory();
})(typeof self !== "undefined" ? self : this, function () {
  // モデルの点 → 地面の2D座標
  function groundOf(m, ySign) {
    return [m[0], -ySign * m[2]];
  }

  // 対応点（{u:[x,y], p:[x,y]}）から、s・theta（ラジアン）・tx・ty を最小二乗で求める（2次元のUmeyama法）。
  // 2点あれば決まる。3点以上だと、ずれ（rms_m）で、合わせ具合が分かる。
  function fit(pairs) {
    const n = pairs.length;
    if (n < 2) return { error: "対応点が2つ以上、必要です。" };
    let ux = 0, uy = 0, px = 0, py = 0;
    for (const q of pairs) { ux += q.u[0]; uy += q.u[1]; px += q.p[0]; py += q.p[1]; }
    ux /= n; uy /= n; px /= n; py /= n;
    let a = 0, b = 0, vu = 0;
    for (const q of pairs) {
      const x = q.u[0] - ux, y = q.u[1] - uy, X = q.p[0] - px, Y = q.p[1] - py;
      a += x * X + y * Y;   // 内積
      b += x * Y - y * X;   // 外積
      vu += x * x + y * y;
    }
    if (vu < 1e-12) return { error: "モデル上の点が、近すぎます。離れた点を選んでください。" };
    const norm = Math.hypot(a, b);
    if (norm < 1e-12) return { error: "対応点から、向きを決められません。" };
    const theta = Math.atan2(b, a);
    const s = norm / vu;
    const c = Math.cos(theta), sn = Math.sin(theta);
    const tx = px - s * (c * ux - sn * uy);
    const ty = py - s * (sn * ux + c * uy);
    const T = { s, theta, tx, ty };
    const residuals = pairs.map((q) => {
      const r = uToPlan(T, q.u);
      return Math.hypot(r[0] - q.p[0], r[1] - q.p[1]);
    });
    const rms = Math.sqrt(residuals.reduce((acc, r) => acc + r * r, 0) / n);
    return { ...T, rms, residuals };
  }

  function uToPlan(T, u) {
    const c = Math.cos(T.theta), sn = Math.sin(T.theta);
    return [T.s * (c * u[0] - sn * u[1]) + T.tx, T.s * (sn * u[0] + c * u[1]) + T.ty];
  }

  function planToU(T, p) {
    const c = Math.cos(T.theta), sn = Math.sin(T.theta);
    const x = (p[0] - T.tx) / T.s, y = (p[1] - T.ty) / T.s;
    return [c * x + sn * y, -sn * x + c * y];
  }

  // モデルの点 [mx,my,mz] → フロア図 {x, y, h}（hは床からの高さ(m)）
  function modelToPlan(T, m, ySign, floorY) {
    const p = uToPlan(T, groundOf(m, ySign));
    return { x: p[0], y: p[1], h: ySign * (m[1] - floorY) * T.s };
  }

  // フロア図の点（x, y, 高さh m）→ モデルの点 [mx,my,mz]
  function planToModel(T, x, y, h, ySign, floorY) {
    const u = planToU(T, [x, y]);
    return [u[0], floorY + (ySign * h) / T.s, -ySign * u[1]];
  }

  // 画面の線（カメラ位置 o、向き d）と、床の面（モデルのY=floorY）の交点。交わらなければ null
  function rayToFloor(o, d, floorY) {
    if (Math.abs(d[1]) < 1e-9) return null;
    const t = (floorY - o[1]) / d[1];
    if (!(t > 0)) return null;
    return [o[0] + t * d[0], floorY, o[2] + t * d[2]];
  }

  return { groundOf, fit, uToPlan, planToU, modelToPlan, planToModel, rayToFloor };
});
