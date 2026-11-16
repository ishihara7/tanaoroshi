// 備品タグのページ：自動で記録してよいかの判定。ブラウザでも Node.js（テスト）でも使える。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.TagLogic = factory();
})(typeof self !== "undefined" ? self : this, function () {
  /*
   * ページの開かれ方（navigation type）
   *   "navigate"     : リンクやNFCタグから開いた（タッチ直後）→ 自動で記録する
   *   "reload"       : 再読み込み                              → 記録しない
   *   "back_forward" : 戻る・進む、タブの復元                   → 記録しない
   *   "prerender"    : 先読み                                  → 記録しない
   * 再読み込みやタブの復元のたびに、その場所で記録し直して、備品の位置が書き換わるのを防ぐ。
   */
  function shouldAutoRecord(navType) {
    return navType === "navigate";
  }
  return { shouldAutoRecord };
});
