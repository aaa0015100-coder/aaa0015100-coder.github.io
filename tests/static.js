// 入口頁靜態檢查：node tests/static.js [index.html] [其他 app 的 index.html …]
// 1. 無外部載入、無 localStorage／cookie  2. 色碼只出現在 :root token 區
// 3. 靜態 id 不重複  4. parseMeta 能讀出各 app 的版本與查證日期
const fs = require("fs"), vm = require("vm");
const file = process.argv[2] || "index.html";
const html = fs.readFileSync(file, "utf8");
const fails = [];

if (/<(script|link|img|iframe)[^>]+(src|href)\s*=\s*["']https?:/i.test(html)) fails.push("有外部載入");
if (/fonts\.googleapis|@import/i.test(html)) fails.push("有外部字型");
if (/sessionStorage|document\.cookie|indexedDB/.test(html)) fails.push("使用瀏覽器儲存");
// 入口頁例外：localStorage 只能用 ORDER_KEY，且每次存取都在 try 裡
const lsCalls = [...html.matchAll(/localStorage\.(\w+)\(([^,)]*)/g)];
if (!lsCalls.length) fails.push("找不到順序儲存");
for (const m of lsCalls) if (m[2].trim() !== "ORDER_KEY") fails.push("localStorage 用了 ORDER_KEY 以外的鍵：" + m[0]);
for (const fn of ["loadOrder", "saveOrder"]) {
  const body = (html.match(new RegExp("function " + fn + "\\([^)]*\\)\\{([\\s\\S]*?)\\n\\}")) || [])[1] || "";
  if (!/^\s*try\s*\{/.test(body)) fails.push(fn + " 沒有包 try");
}
if ((html.match(/localStorage/g) || []).length !== lsCalls.length) fails.push("localStorage 出現在預期以外的地方");
if (/<meta[^>]+name=["']claude:/i.test(html)) fails.push("有 claude: meta");
if (!/^<!doctype html>/i.test(html) || !/<html lang="zh-Hant">/.test(html) || !/viewport-fit=cover/.test(html)) fails.push("外層缺 doctype／lang／viewport");

const css = html.match(/<style>([\s\S]*?)<\/style>/)[1];
const noTok = css.replace(/:root[^{]*\{[^}]*\}/g, "").replace(/@media \(prefers-color-scheme: dark\)\{:root[^{]*\{[^}]*\}\}/g, "");
const hard = noTok.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g);
if (hard) fails.push("token 以外的色碼：" + hard.join(" "));

const ids = [...html.replace(/<script>[\s\S]*<\/script>/, "").matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
if (dup.length) fails.push("重複 id：" + dup.join(","));

const js = html.match(/<script>([\s\S]*)<\/script>/)[1];
const ctx = {}; vm.createContext(ctx);
vm.runInContext(js + "\n;this.__api={APPS,parseMeta,daysSince,card,mergeOrder,moveId,DEFAULT_ORDER};", ctx);
const A = ctx.__api;
// 順序邏輯
const D = A.DEFAULT_ORDER.join();
const mo = x => A.mergeOrder(x).join();
if (mo(null) !== D) fails.push("mergeOrder(null)");
if (mo("abc") !== D) fails.push("mergeOrder 非陣列");
if (mo(["oncall-helper"]) !== "oncall-helper,pca-helper,abx-helper") fails.push("mergeOrder 新 app 接在最後");
if (mo(["x-old", "abx-helper", "abx-helper"]) !== "abx-helper,pca-helper,oncall-helper") fails.push("mergeOrder 去除未知與重複");
if (A.moveId(A.DEFAULT_ORDER, "pca-helper", -1).join() !== D) fails.push("moveId 頂端上移應不變");
if (A.moveId(A.DEFAULT_ORDER, "pca-helper", 1).join() !== "abx-helper,pca-helper,oncall-helper") fails.push("moveId 下移");
if (A.moveId(A.DEFAULT_ORDER, "oncall-helper", 1).join() !== D) fails.push("moveId 底端下移應不變");
const t = A.parseMeta('const APP_VERSION = "1.7";\nconst CHECKED = "2026-10-18";');
if (t.v !== "1.7" || t.d !== "2026-10-18") fails.push("parseMeta pca 格式失敗");
const u = A.parseMeta('const VERIFIED = "2026-10-25";\nconst VERSION = "v0.15";');
if (u.v !== "0.15" || u.d !== "2026-10-25") fails.push("parseMeta abx 格式失敗");
const w = A.parseMeta('const APP_VERSION="1.2";const CHECKED = "2026-10-24";');
if (w.v !== "1.2" || w.d !== "2026-10-24") fails.push("parseMeta oncall 格式失敗");
const BAD = /undefined|NaN|\[object|null(?![\w-])/;
for (const a of A.APPS) for (const m of [null, { v:null, d:null }, { v:"1.0", d:"2020-01-01" }, { v:"1.0", d:"2099-01-01" }]) {
  const h = A.card(a, m).replace(/<[^>]+>/g, " ");
  if (BAD.test(h)) fails.push(`card ${a.id} ${JSON.stringify(m)} 出現 ${h.match(BAD)[0]}`);
}

// 實際 app 檔（若有提供）：確認讀得到
for (const f of process.argv.slice(3)) {
  const m = A.parseMeta(fs.readFileSync(f, "utf8"));
  if (!m.v || !m.d) fails.push(`${f} 讀不到版本或查證日期`);
}

console.log(fails.length ? "STATIC FAIL\n" + fails.join("\n") : "STATIC OK");
process.exit(fails.length ? 1 : 0);
