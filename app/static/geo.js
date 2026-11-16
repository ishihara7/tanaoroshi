// 位置情報テスト：スキャンした瞬間の1回だけ取得する（継続追跡はしない）
(function () {
  const btn = document.getElementById("go");
  const out = document.getElementById("result");
  const label = document.getElementById("label");

  function show(html) { out.innerHTML = html; }

  async function save(payload) {
    const res = await fetch("/test/geo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("保存に失敗しました（" + res.status + "）");
  }

  btn.addEventListener("click", function () {
    if (!("geolocation" in navigator)) {
      show('<span class="err">この端末は位置情報に対応していません。</span>');
      return;
    }
    btn.disabled = true;
    show("取得中…");
    navigator.geolocation.getCurrentPosition(
      async function (pos) {
        const c = pos.coords;
        const payload = {
          label: label.value,
          latitude: c.latitude,
          longitude: c.longitude,
          accuracy_m: c.accuracy,
          altitude: c.altitude,
        };
        show(
          "緯度: " + c.latitude.toFixed(6) + "<br>経度: " + c.longitude.toFixed(6) +
          "<br>誤差: " + Math.round(c.accuracy) + " m" +
          "<br>高度: " + (c.altitude == null ? "取得できません" : Math.round(c.altitude) + " m")
        );
        try { await save(payload); show(out.innerHTML + "<br>保存しました。再読み込みで一覧に反映されます。"); }
        catch (e) { show(out.innerHTML + '<br><span class="err">' + e.message + "</span>"); }
        btn.disabled = false;
      },
      async function (err) {
        // 拒否・タイムアウト時は位置情報なしで記録する
        show('<span class="err">取得できませんでした：' + err.message + "</span>");
        try { await save({ label: label.value, error_message: err.message.slice(0, 200) }); } catch (e) {}
        btn.disabled = false;
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
  });
})();
