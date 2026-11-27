// model_align.js の計算を確かめる（Node.js、追加のライブラリなし）。使い方：node tests/js/model_align_test.js
const assert = require("assert");
const A = require("../../app/static/model_align.js");

const close = (a, b, eps = 1e-6, msg = "") => assert.ok(Math.abs(a - b) < eps, `${msg} ${a} != ${b}`);

// 本当の変換：縮尺0.37、回転53度、平行移動（モデルは、Y軸が上）
const truth = { s: 1 / 0.37, theta: (53 * Math.PI) / 180, tx: 4.2, ty: -1.3 };
const plan = [[0, 0], [10, 0], [10, 6], [0, 6]];
for (const ySign of [1, -1]) {
  const floorY = 0.8;
  const models = plan.map(([x, y]) => A.planToModel(truth, x, y, 0, ySign, floorY));

  // 往復で元に戻る
  plan.forEach(([x, y], i) => {
    const back = A.modelToPlan(truth, models[i], ySign, floorY);
    close(back.x, x); close(back.y, y); close(back.h, 0, 1e-6, "高さ");
  });

  // 点から変換を復元できる
  const pairs = models.map((m, i) => ({ u: A.groundOf(m, ySign), p: plan[i] }));
  const f = A.fit(pairs);
  close(f.s, truth.s); close(f.theta, truth.theta); close(f.tx, truth.tx); close(f.ty, truth.ty);
  assert.ok(f.rms < 1e-9);

  // 高さ1.2mの点は、床から1.2mの位置になる
  const m = A.planToModel(f, 3, 2, 1.2, ySign, floorY);
  close(A.modelToPlan(f, m, ySign, floorY).h, 1.2);
}

// 2点でも決まる
{
  const u = [[0, 0], [1, 0]], p = [[2, 3], [2, 5]];  // 縮尺2、90度回転
  const f = A.fit([{ u: u[0], p: p[0] }, { u: u[1], p: p[1] }]);
  close(f.s, 2); close(f.theta, Math.PI / 2); close(f.tx, 2); close(f.ty, 3);
}

// ずれのある点では、rmsが大きくなる
{
  const pairs = [{ u: [0, 0], p: [0, 0] }, { u: [1, 0], p: [1, 0] }, { u: [1, 1], p: [1, 1] }, { u: [0, 1], p: [0.5, 1.5] }];
  assert.ok(A.fit(pairs).rms > 0.1);
}

// 異常な入力
assert.ok(A.fit([{ u: [0, 0], p: [0, 0] }]).error);
assert.ok(A.fit([{ u: [1, 1], p: [0, 0] }, { u: [1, 1], p: [5, 5] }]).error);

// 床との交点
{
  const hit = A.rayToFloor([1, 10, 2], [0, -1, 0], 0);
  assert.deepStrictEqual(hit, [1, 0, 2]);
  assert.strictEqual(A.rayToFloor([0, 1, 0], [1, 0, 0], 0), null);  // 平行
  assert.strictEqual(A.rayToFloor([0, 1, 0], [0, 1, 0], 0), null);  // 後ろ向き
}

console.log("model_align: OK");
