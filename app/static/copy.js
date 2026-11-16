// 「コピー」ボタン：data-copy-target で指定した要素の文字を、クリップボードにコピーする。
(function () {
  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    // 古いブラウザ向けの代替（選択して、コピーのコマンドを実行する）
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, text.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    if (!ok) throw new Error("copy failed");
  }

  document.querySelectorAll("[data-copy-target]").forEach(function (btn) {
    const label = btn.textContent;
    btn.addEventListener("click", async function () {
      const target = document.getElementById(btn.dataset.copyTarget);
      try {
        await copyText(target.textContent.trim());
        btn.textContent = "コピーしました";
      } catch (e) {
        // コピーできないときは、文字を選択して、手動でコピーできるようにする
        const range = document.createRange();
        range.selectNodeContents(target);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        btn.textContent = "選択しました（長押しでコピー）";
      }
      setTimeout(function () { btn.textContent = label; }, 2500);
    });
  });
})();
