// tag.js の動きを、ブラウザを模した環境で確かめる（Node.js、追加のライブラリなし）。
// 使い方：node tag_flow_harness.js <シナリオ>
//   remembered     : 端末に社員番号が記憶されている → 位置が取れ次第、自動で送信する
//   not_remembered : 記憶なし → 位置が取れても、送信しない。入力して「記録する」で送信する
//   invalid_number : 不正な社員番号では、ボタンを押しても送信しない
//   reload         : 再読み込みでは、自動で記録しない
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const scenario = process.argv[2];
const STATIC = path.join(__dirname, "..", "..", "app", "static");

function makeEl(extra = {}) {
  const listeners = {};
  return Object.assign({
    className: "", textContent: "", value: "", disabled: false, dataset: {}, listeners,
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    fire(type, ev = {}) { (listeners[type] || []).forEach((fn) => fn(ev)); },
    click() { if (!this.disabled) this.fire("click"); },
    focus() { this.focused = true; },
  }, extra);
}

const els = {
  status: makeEl({ dataset: { token: "TOKEN123" } }),
  "status-text": makeEl(), detail: makeEl(), "record-btn": makeEl(),
  "employee-no": makeEl(), "submit-btn": makeEl({ disabled: true }),
};
const store = {};
const fetchCalls = [];
const navType = scenario === "reload" ? "reload" : "navigate";

const sandbox = {
  console,
  document: { getElementById: (id) => els[id], querySelector: () => ({ content: "csrf-token" }) },
  window: { addEventListener() {} },
  navigator: {
    geolocation: {
      watchPosition(ok) {  // 誤差8mの位置が、すぐに取れる
        setTimeout(() => ok({ coords: { latitude: 36.29, longitude: 139.37, accuracy: 8, altitude: null } }), 5);
        return 1;
      },
      clearWatch() {},
    },
  },
  performance: { getEntriesByType: () => [{ type: navType }] },
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } },
  fetch: async (url, opts) => {
    fetchCalls.push({ url, body: JSON.parse(opts.body) });
    return { ok: true, json: async () => ({ ok: true, deduped: false, position: true }) };
  },
  setTimeout, clearTimeout, setInterval, clearInterval, Date, JSON, Math, String, Object,
};
sandbox.window.TagLogic = require(path.join(STATIC, "tag_logic.js"));
sandbox.window.localStorage = sandbox.localStorage;

if (scenario === "remembered") store["tanaoroshi.employee_no"] = "E1001";

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(STATIC, "tag.js"), "utf8"), sandbox);

if (scenario === "typed_early") {
  // 位置が取れる前（調べている最中）に、社員番号を打ち始めた。記憶はない。
  els["employee-no"].value = "E7";
  els["employee-no"].fire("input");
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const out = { scenario, stages: [] };
  const snap = (label) => out.stages.push({
    label, calls: fetchCalls.length, status: els.status.className, text: els["status-text"].textContent,
    buttonDisabled: els["submit-btn"].disabled, input: els["employee-no"].value,
  });
  await wait(80);
  snap("位置が取れたあと");

  if (scenario === "not_remembered") {
    els["employee-no"].value = "E77";
    els["employee-no"].fire("input");
    snap("社員番号を入力した直後（まだ送信しない）");
    els["submit-btn"].click();
    await wait(50);
    snap("「記録する」を押したあと");
  }
  if (scenario === "typed_early") {
    els["submit-btn"].click();
    await wait(50);
    snap("「記録する」を押したあと");
  }
  if (scenario === "invalid_number") {
    els["employee-no"].value = "社員1";
    els["employee-no"].fire("input");
    els["submit-btn"].click();  // 無効なので、押せない
    await wait(30);
    snap("不正な番号で、押したあと");
  }
  out.calls = fetchCalls;
  out.stored = store["tanaoroshi.employee_no"] || "";
  console.log(JSON.stringify(out));
  process.exit(0);
})();
