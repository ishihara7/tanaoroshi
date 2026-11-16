// 備品タグ：開いた瞬間に、位置を1回だけ取得して記録する（継続追跡はしない）
(function () {
  const status = document.getElementById("status");
  const detail = document.getElementById("detail");
  const token = status.dataset.token;
  const csrf = document.querySelector('meta[name="csrf"]').content;

  async function send(payload) {
    const res = await fetch("/i/" + encodeURIComponent(token) + "/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.message || "記録に失敗しました（" + res.status + "）");
    return body;
  }

  function done(body, accuracy) {
    if (body.position) {
      status.textContent = "所在を記録しました。";
      detail.textContent = accuracy != null
        ? "位置の誤差は約" + Math.round(accuracy) + "mです（おおよその位置です）。" : "";
    } else {
      status.textContent = "確認を記録しました（位置は取得できませんでした）。";
      detail.textContent = "位置情報の許可と、端末の位置情報サービスを確認してください。";
    }
  }

  function fail(e) { status.textContent = e.message; status.style.borderColor = "var(--err)"; }

  if (!("geolocation" in navigator)) {
    send({ error_message: "位置情報に対応していません" }).then((b) => done(b)).catch(fail);
    return;
  }
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      const c = pos.coords;
      send({ latitude: c.latitude, longitude: c.longitude, accuracy_m: c.accuracy, altitude: c.altitude })
        .then((b) => done(b, c.accuracy)).catch(fail);
    },
    function (err) {
      // 拒否・タイムアウト時は、位置なしで記録する
      const kinds = { 1: "許可されていません", 2: "位置を取得できません", 3: "時間切れ" };
      send({ error_message: "コード" + err.code + "：" + (kinds[err.code] || "不明") })
        .then((b) => done(b)).catch(fail);
    },
    { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
  );
})();
