// 備品タグ：タッチして開いたときだけ、自動で記録を始める。
// 位置は、タッチ直後の数秒間（最大8秒）だけ取り続け、一番精度のよい1件を送る（継続追跡ではない）。
// 位置を調べている間に、社員番号を入力してもらい、記録と一緒に保存する（2回目以降は、この端末に記憶）。
// 再読み込み・戻る操作・タブの復元では、自動では記録しない（ボタンを押したときだけ記録する）。
(function () {
  const T = window.TagLogic;
  const box = document.getElementById("status");        // 状態の枠（色とアイコンが、状態で変わる）
  const text = document.getElementById("status-text");  // 状態のメッセージ
  const detail = document.getElementById("detail");
  const again = document.getElementById("record-btn");   // 今の場所で記録し直す
  const empInput = document.getElementById("employee-no");
  const submitBtn = document.getElementById("submit-btn"); // 記録する
  const token = box.dataset.token;
  const csrf = document.querySelector('meta[name="csrf"]').content;
  const STORE_KEY = "tanaoroshi.employee_no";

  // 社員番号の記憶（この端末のブラウザだけ。取得できない環境でも、動作に影響しない）
  function loadEmployeeNo() { try { return localStorage.getItem(STORE_KEY) || ""; } catch (e) { return ""; } }
  function saveEmployeeNo(v) { try { localStorage.setItem(STORE_KEY, v); } catch (e) { /* 保存できなくても、記録は続ける */ } }

  // 状態：busy（調べている）／wait（入力待ち）／ok（記録した）／error（失敗）
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

  let running = false;   // 位置を調べている最中
  let sending = false;   // 送信中
  let watchId = null;
  let timerId = null;
  let pending = null;    // 位置の取得が終わった結果（送信待ち）
  let autoSend = false;  // 位置が取れ次第、自動で送信するか

  function updateButton() { submitBtn.disabled = sending || !T.validEmployeeNo(empInput.value); }

  function stopWatching() {
    if (watchId != null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
    if (timerId != null) { clearInterval(timerId); timerId = null; }
  }
  window.addEventListener("pagehide", stopWatching);

  // 社員番号と一緒に、記録を送信する
  function sendPending() {
    if (!pending || sending) return;
    const emp = empInput.value.trim();
    if (!T.validEmployeeNo(emp)) {
      setStatus("wait", "社員番号を入力して、「記録する」を押してください。");
      return;
    }
    sending = true; updateButton(); again.disabled = true;
    const { payload, accuracy } = pending;
    send(Object.assign({}, payload, { employee_no: emp }))
      .then((b) => { saveEmployeeNo(emp); pending = null; done(b, accuracy); })
      .catch(fail)
      .finally(() => { sending = false; again.disabled = false; updateButton(); });
  }

  // 位置の取得が終わった（位置あり、または、位置なし）
  function onPositionDecided(payload, accuracy) {
    stopWatching();
    running = false;
    pending = { payload, accuracy };
    if (T.afterPosition(autoSend, empInput.value) === "send") {
      sendPending();
    } else {
      setStatus("wait", "位置を取得しました。社員番号を入力して、「記録する」を押してください。");
      empInput.focus();
    }
  }

  // 位置を取り続けて、一番精度のよい1件を、記録の候補にする
  function record(auto) {
    if (running || sending) return;
    running = true;
    pending = null;
    autoSend = auto && T.validEmployeeNo(empInput.value);
    detail.textContent = "";
    updateButton();

    if (!("geolocation" in navigator)) {
      onPositionDecided({ error_message: "位置情報に対応していません" }, null);
      return;
    }
    const fixes = [];
    const started = Date.now();
    const waiting = () => (T.validEmployeeNo(empInput.value) ? "" : "（社員番号を入力してください）");
    setStatus("busy", "位置を調べています…" + waiting());

    function conclude() {
      const verdict = T.decide(T.pickBest(fixes), Date.now() - started);
      if (verdict === "continue") return false;
      const best = T.pickBest(fixes);
      if (best) onPositionDecided({ latitude: best.lat, longitude: best.lon, accuracy_m: best.accuracy, altitude: best.altitude }, best.accuracy);
      else onPositionDecided({ error_message: "位置を取得できません（時間切れ）" }, null);
      return true;
    }

    watchId = navigator.geolocation.watchPosition(
      function (pos) {
        const c = pos.coords;
        fixes.push({ lat: c.latitude, lon: c.longitude, accuracy: c.accuracy, altitude: c.altitude });
        const best = T.pickBest(fixes);
        setStatus("busy", "位置を調べています…（誤差 約" + Math.round(best.accuracy) + "m）" + waiting());
        conclude();
      },
      function (err) {
        // 拒否されたときは、すぐに、位置なしの結果にする。それ以外は、時間まで待って、取れた分で判断する
        if (err.code === 1) onPositionDecided({ error_message: "コード1：許可されていません" }, null);
      },
      { enableHighAccuracy: true, timeout: T.HARD_TIMEOUT_MS, maximumAge: 0 }
    );
    // 新しい位置が来なくても、時間で終えられるように、定期的に判定する
    timerId = setInterval(conclude, 500);
  }

  // 「記録する」：位置が取れていれば送信。まだなら、取れ次第、自動で送信する
  submitBtn.addEventListener("click", function () {
    if (!T.validEmployeeNo(empInput.value)) return;
    if (pending) sendPending();
    else if (running) { autoSend = true; setStatus("busy", "位置の取得が終わりしだい、記録します…"); }
    else record(true);
  });
  empInput.addEventListener("input", updateButton);
  empInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); submitBtn.click(); } });
  again.addEventListener("click", function () { record(true); });

  // 記憶していた社員番号を入力欄に入れる
  empInput.value = loadEmployeeNo();
  updateButton();

  const nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
  const navType = nav ? nav.type : "navigate";
  if (T.shouldAutoRecord(navType)) {
    record(true);  // 記憶した社員番号があれば、位置が取れ次第、自動で記録する
  } else {
    setStatus("busy", "再読み込みのため、記録していません。");
    box.className = "status";  // 記録中ではないので、回転表示は出さない
    detail.textContent = "記録するには、社員番号を入力して「記録する」を押すか、もう一度タグにタッチしてください。";
  }
})();
