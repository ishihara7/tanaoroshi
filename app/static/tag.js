// 備品タグ：タッチして開いたときだけ、自動で記録する。
// 位置は、タッチ直後の数秒間（最大8秒）だけ取り続け、一番精度のよい1件を送る（継続追跡ではない）。
// 再読み込み・戻る操作・タブの復元では、自動では記録しない（ボタンを押したときだけ記録する）。
(function () {
  const T = window.TagLogic;
  const box = document.getElementById("status");        // 状態の枠（色とアイコンが、状態で変わる）
  const text = document.getElementById("status-text");  // 状態のメッセージ
  const detail = document.getElementById("detail");
  const again = document.getElementById("record-btn");
  const token = box.dataset.token;
  const csrf = document.querySelector('meta[name="csrf"]').content;

  // 状態：busy（調べている）／ok（記録した）／error（失敗）
  function setStatus(kind, message) {
    box.className = "status is-" + kind;
    text.textContent = message;
  }

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
      setStatus("ok", "さきほど記録しました。");
      detail.textContent = "";
    } else if (body.position) {
      setStatus("ok", "所在を記録しました。");
      detail.textContent = accuracy != null
        ? "位置の誤差は約" + Math.round(accuracy) + "mです（おおよその位置です）。" : "";
    } else {
      setStatus("error", "確認を記録しました（位置は取得できませんでした）。");
      detail.textContent = "位置情報の許可と、端末の位置情報サービスを確認してください。";
    }
  }

  function fail(e) { setStatus("error", e.message); }

  let running = false;
  let watchId = null;
  let timerId = null;

  function stopWatching() {
    if (watchId != null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
    if (timerId != null) { clearInterval(timerId); timerId = null; }
  }
  window.addEventListener("pagehide", stopWatching);

  // 位置を取り続けて、一番精度のよい1件で記録する
  function record() {
    if (running) return;
    running = true;
    again.disabled = true;
    detail.textContent = "";
    const finish = () => { stopWatching(); running = false; again.disabled = false; };
    const sendAndShow = (payload, accuracy) =>
      send(payload).then((b) => done(b, accuracy)).catch(fail).finally(finish);

    if (!("geolocation" in navigator)) {
      stopWatching();
      sendAndShow({ error_message: "位置情報に対応していません" });
      return;
    }

    const fixes = [];
    const started = Date.now();
    setStatus("busy", "位置を調べています…");

    function conclude() {
      const verdict = T.decide(T.pickBest(fixes), Date.now() - started);
      if (verdict === "continue") return false;
      stopWatching();
      const best = T.pickBest(fixes);
      if (best) {
        sendAndShow({ latitude: best.lat, longitude: best.lon, accuracy_m: best.accuracy, altitude: best.altitude }, best.accuracy);
      } else {
        sendAndShow({ error_message: "位置を取得できません（時間切れ）" });
      }
      return true;
    }

    watchId = navigator.geolocation.watchPosition(
      function (pos) {
        const c = pos.coords;
        fixes.push({ lat: c.latitude, lon: c.longitude, accuracy: c.accuracy, altitude: c.altitude });
        const best = T.pickBest(fixes);
        setStatus("busy", "位置を調べています…（誤差 約" + Math.round(best.accuracy) + "m）");
        conclude();
      },
      function (err) {
        // 拒否されたときは、すぐに、位置なしで記録する。それ以外は、時間まで待って、取れた分で判断する
        if (err.code === 1) {
          stopWatching();
          sendAndShow({ error_message: "コード1：許可されていません" });
        }
      },
      { enableHighAccuracy: true, timeout: T.HARD_TIMEOUT_MS, maximumAge: 0 }
    );
    // 新しい位置が来なくても、時間で終えられるように、定期的に判定する
    timerId = setInterval(conclude, 500);
  }

  again.addEventListener("click", record);

  const nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
  const navType = nav ? nav.type : "navigate";
  if (T.shouldAutoRecord(navType)) {
    record();
  } else {
    setStatus("busy", "再読み込みのため、記録していません。");
    box.className = "status";  // 記録中ではないので、回転表示は出さない
    detail.textContent = "今の場所で記録するには、下のボタンを押すか、もう一度タグにタッチしてください。";
  }
})();
