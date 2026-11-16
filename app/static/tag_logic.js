// 備品タグのページの判定ロジック。ブラウザでも Node.js（テスト）でも使える。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.TagLogic = factory();
})(typeof self !== "undefined" ? self : this, function () {
  const TARGET_ACCURACY_M = 10;  // この誤差（m）以下になったら、そこで取得を終える
  const MAX_WAIT_MS = 8000;      // 位置を取り続ける最大の時間（取れていれば、ここで終える）
  const HARD_TIMEOUT_MS = 20000; // 1件も取れないときに、あきらめるまでの時間

  /*
   * ページの開かれ方（navigation type）
   *   "navigate"     : リンクやNFCタグから開いた（タッチ直後）→ 自動で記録する
   *   "reload"       : 再読み込み / "back_forward" : 戻る・進む・タブの復元 / "prerender" : 先読み → 記録しない
   * 再読み込みやタブの復元のたびに、その場所で記録し直して、備品の位置が書き換わるのを防ぐ。
   */
  function shouldAutoRecord(navType) {
    return navType === "navigate";
  }

  // 取れた位置のうち、一番精度のよいもの（誤差が最小）を選ぶ。同じ誤差なら、新しい方。
  function pickBest(fixes) {
    let best = null;
    for (const f of fixes) {
      if (f == null || typeof f.accuracy !== "number") continue;
      if (best === null || f.accuracy <= best.accuracy) best = f;
    }
    return best;
  }

  /*
   * 取得を続けるか、終えるかの判定
   *   "continue" : まだ待つ
   *   "finish"   : 今の最良の位置で記録する
   *   "giveup"   : 位置が1件も取れないまま、時間切れ
   */
  function decide(best, elapsedMs) {
    if (best && best.accuracy <= TARGET_ACCURACY_M) return "finish";
    if (best && elapsedMs >= MAX_WAIT_MS) return "finish";
    if (!best && elapsedMs >= HARD_TIMEOUT_MS) return "giveup";
    return "continue";
  }

  return { TARGET_ACCURACY_M, MAX_WAIT_MS, HARD_TIMEOUT_MS, shouldAutoRecord, pickBest, decide };
});
