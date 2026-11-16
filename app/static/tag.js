// 備品タグ：タッチして開いたときだけ、位置を1回取得して自動で記録する（継続追跡はしない）。
// 再読み込み・戻る操作・タブの復元では、自動では記録しない（ボタンを押したときだけ記録する）。
(function () {
  const status = document.getElementById("status");
  const detail = document.getElementById("detail");
  const again = document.getElementById("record-btn");
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
    if (body.deduped) {
      status.textContent = "さきほど記録しました。";
      detail.textContent = "";
    } else if (body.position) {
      status.textContent = "所在を記録しました。";
      detail.textContent = accuracy != null
        ? "位置の誤差は約" + Math.round(accuracy) + "mです（おおよその位置です）。" : "";
    } else {
      status.textContent = "確認を記録しました（位置は取得できませんでした）。";
      detail.textContent = "位置情報の許可と、端末の位置情報サービスを確認してください。";
    }
    status.style.borderColor = "";
  }

  function fail(e) { status.textContent = e.message; status.style.borderColor = "var(--err)"; }

  // 位置を1回だけ取得して、記録する
  function record() {
    again.disabled = true;
    status.textContent = "所在を記録しています…";
    detail.textContent = "";
    const finish = () => { again.disabled = false; };
    if (!("geolocation" in navigator)) {
      send({ error_message: "位置情報に対応していません" }).then((b) => done(b)).catch(fail).finally(finish);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        const c = pos.coords;
        send({ latitude: c.latitude, longitude: c.longitude, accuracy_m: c.accuracy, altitude: c.altitude })
          .then((b) => done(b, c.accuracy)).catch(fail).finally(finish);
      },
      function (err) {
        // 拒否・タイムアウト時は、位置なしで記録する
        const kinds = { 1: "許可されていません", 2: "位置を取得できません", 3: "時間切れ" };
        send({ error_message: "コード" + err.code + "：" + (kinds[err.code] || "不明") })
          .then((b) => done(b)).catch(fail).finally(finish);
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
  }

  again.addEventListener("click", record);

  const nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
  const navType = nav ? nav.type : "navigate";
  if (window.TagLogic.shouldAutoRecord(navType)) {
    record();
  } else {
    status.textContent = "再読み込みのため、記録していません。";
    detail.textContent = "今の場所で記録するには、下のボタンを押すか、もう一度タグにタッチしてください。";
  }
})();
