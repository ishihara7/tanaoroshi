// レーダーの計算（距離・方位・見せ方）。ブラウザでも Node.js（テスト）でも使える。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RadarMath = factory();
})(typeof self !== "undefined" ? self : this, function () {
  const R = 6371000;
  const rad = (d) => (d * Math.PI) / 180;
  const deg = (r) => (r * 180) / Math.PI;

  // 2点間の距離（m）
  function distanceM(lat1, lon1, lat2, lon2) {
    const dp = rad(lat2 - lat1), dl = rad(lon2 - lon1);
    const h = Math.sin(dp / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dl / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  // 1点目から2点目への方位（度）。北が0、時計回り
  function bearingDeg(lat1, lon1, lat2, lon2) {
    const dl = rad(lon2 - lon1);
    const y = Math.sin(dl) * Math.cos(rad(lat2));
    const x = Math.cos(rad(lat1)) * Math.sin(rad(lat2)) - Math.sin(rad(lat1)) * Math.cos(rad(lat2)) * Math.cos(dl);
    return (deg(Math.atan2(y, x)) + 360) % 360;
  }

  const COMPASS = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"];
  function compassName(b) { return COMPASS[Math.round((((b % 360) + 360) % 360) / 45) % 8]; }

  const RELATIVE = ["前", "右前", "右", "右後ろ", "後ろ", "左後ろ", "左", "左前"];
  function relativeName(angle) { return RELATIVE[Math.round((((angle % 360) + 360) % 360) / 45) % 8]; }

  // 2つの位置の誤差を合成した、方向の確からしさの目安（m）
  function combinedAccuracy(a, b) { return Math.sqrt((a || 0) ** 2 + (b || 0) ** 2); }

  // 目盛り（m）。備品までの距離が、図の外に出ないように選ぶ
  const STEPS = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];
  function scaleFor(distance) {
    for (const s of STEPS) if (distance * 1.15 <= s) return s;
    return STEPS[STEPS.length - 1];
  }

  // 距離の表示
  function formatDistance(m) {
    if (m < 1000) return "約" + Math.round(m) + "m";
    return "約" + (m / 1000).toFixed(1) + "km";
  }

  /*
   * 状態の判定
   *   "unknown"  : 備品の位置の記録がない
   *   "within"   : 距離が誤差以内。方向は当てにならない（近くにいる）
   *   "ok"       : 方向を示してよい
   */
  function judge(me, asset) {
    if (asset.lat == null || asset.lon == null) return { state: "unknown" };
    const distance = distanceM(me.lat, me.lon, asset.lat, asset.lon);
    const uncertainty = combinedAccuracy(me.accuracy, asset.accuracy);
    const bearing = bearingDeg(me.lat, me.lon, asset.lat, asset.lon);
    return { state: distance <= uncertainty ? "within" : "ok", distance, uncertainty, bearing };
  }

  return { distanceM, bearingDeg, compassName, relativeName, combinedAccuracy, scaleFor, formatDistance, judge };
});
