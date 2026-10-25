# 入口頁瀏覽器測試：python3 tests/e2e.py <hub/index.html> [app 根目錄] [截圖資料夾]
# 建一個暫時網站：/ ＝入口頁，/pca-helper/、/abx-helper/ 用實際 app，/oncall-helper/ 故意缺（測讀取失敗）
import sys, os, shutil, tempfile, threading, functools, http.server, re
from playwright.sync_api import sync_playwright

HUB = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "index.html")
APPS_ROOT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else None
SHOT = sys.argv[3] if len(sys.argv) > 3 else None

site = tempfile.mkdtemp()
shutil.copy(HUB, os.path.join(site, "index.html"))
expect = {}
for app in ["pca-helper", "abx-helper"]:
    src = os.path.join(APPS_ROOT, app, "index.html") if APPS_ROOT else None
    if src and os.path.exists(src):
        os.makedirs(os.path.join(site, app))
        shutil.copy(src, os.path.join(site, app, "index.html"))
        t = open(src, encoding="utf8").read()
        v = re.search(r'\b(?:APP_VERSION|VERSION)\s*=\s*["\']v?(\d+(?:\.\d+)+)', t).group(1)
        d = re.search(r'\b(?:CHECKED|VERIFIED)\s*=\s*["\'](\d{4}-\d{2}-\d{2})', t).group(1)
        expect[app] = ("v" + v, d)
expect["oncall-helper"] = ("—", "—")

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/"

issues, errs, ext = [], [], []
with sync_playwright() as p:
    b = p.chromium.launch()
    for W in [390, 1280, 320]:
        for scheme in (["light", "dark"] if W == 390 else ["light"]):
            pg = b.new_page(viewport={"width": W, "height": 800}, color_scheme=scheme)
            pg.on("pageerror", lambda e: errs.append(f"{W}:{e}"))
            pg.on("console", lambda m: errs.append(f"{W}:{m.text}") if m.type == "error" and "404" not in m.text else None)
            pg.on("request", lambda r: ext.append(r.url) if not r.url.startswith(URL) else None)
            pg.goto(URL)
            pg.wait_for_function("document.querySelectorAll('[data-k=v]').length===3 && ![...document.querySelectorAll('[data-k]')].some(e=>e.textContent.includes('讀取中'))", timeout=10000)
            for app, (v, d) in expect.items():
                gv = pg.text_content(f'[data-app="{app}"] [data-k=v]').strip()
                gd = pg.text_content(f'[data-app="{app}"] [data-k=d]').strip()
                if (gv, gd) != (v, d): issues.append(f"{W}{scheme} {app}: {gv} {gd} ≠ {v} {d}")
                href = pg.get_attribute(f'[data-app="{app}"] a.btn', "href")
                if href != f"/{app}/": issues.append(f"{app} 連結 {href}")
            if "讀不到版本" not in pg.text_content('[data-app="oncall-helper"]'): issues.append("缺讀不到標示")
            if "讀不到版本" not in pg.text_content("#stat"): issues.append("缺狀態說明")
            body = pg.inner_text("body")
            if re.search(r"undefined|NaN|\[object", body): issues.append(f"{W} 文字異常")
            sw = pg.evaluate("document.documentElement.scrollWidth")
            if sw > W: issues.append(f"{W}{scheme} 橫向溢出 {sw}")
            if W == 390 and scheme == "light":
                for want in ["淺色", "深色", "自動"]:
                    pg.click("#theme")
                    if want not in pg.text_content("#theme"): issues.append(f"主題切換 {want}")
                bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
                if bg != "rgb(237, 241, 240)": issues.append(f"自動主題背景 {bg}")
            if W == 390 and scheme == "light":
                order = lambda: pg.eval_on_selector_all("#apps .app", "els=>els.map(e=>e.dataset.app).join()")
                D = "pca-helper,abx-helper,oncall-helper"
                if order() != D: issues.append("預設順序 " + order())
                if pg.locator("[data-mv]").count(): issues.append("非調整模式出現 ↑↓")
                pg.click("#edit")
                if pg.is_hidden("#ebar") or pg.locator("[data-mv]").count() != 6: issues.append("調整模式未顯示")
                if not pg.is_disabled('[data-id="pca-helper"][data-mv="-1"]') or not pg.is_disabled('[data-id="oncall-helper"][data-mv="1"]'): issues.append("頂／底按鈕未停用")
                pg.click('[data-id="oncall-helper"][data-mv="-1"]'); pg.click('[data-id="oncall-helper"][data-mv="-1"]')
                if order() != "oncall-helper,pca-helper,abx-helper": issues.append("上移後 " + order())
                foc = pg.evaluate("document.activeElement.dataset.id||''")
                if foc != "oncall-helper": issues.append("移動後焦點 " + foc)
                if pg.evaluate("document.documentElement.scrollWidth") > W: issues.append("調整模式溢出")
                pg.click("#done")
                if pg.locator("[data-mv]").count() or not pg.is_hidden("#ebar"): issues.append("完成後仍在調整模式")
                pg.reload(); pg.wait_for_selector("#apps .app")
                if order() != "oncall-helper,pca-helper,abx-helper": issues.append("重新整理後未保留 " + order())
                ls = pg.evaluate("Object.keys(localStorage).join()")
                if ls != "hub-order": issues.append("localStorage 鍵 " + ls)
                pg.click("#edit"); pg.click("#reset")
                if order() != D: issues.append("恢復預設後 " + order())
                if pg.evaluate("localStorage.length") != 0: issues.append("恢復預設未清除儲存")
                pg.click("#done")
                if SHOT:
                    pg.click("#edit"); pg.screenshot(path=os.path.join(SHOT, "hub_390_edit.png"), full_page=True); pg.click("#done")
            if W == 390 and scheme == "dark":
                bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
                if bg != "rgb(14, 21, 20)": issues.append(f"深色背景 {bg}")
            if SHOT:
                os.makedirs(SHOT, exist_ok=True)
                pg.screenshot(path=os.path.join(SHOT, f"hub_{W}_{scheme}.png"), full_page=True)
            pg.close()
    # 儲存不可用（私密模式、封鎖網站資料）：頁面照常、調整仍可用
    pg = b.new_page(viewport={"width": 390, "height": 800})
    pg.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
    pg.on("pageerror", lambda e: errs.append(f"nols:{e}"))
    pg.goto(URL); pg.wait_for_selector("#apps .app")
    pg.click("#edit"); pg.click('[data-id="pca-helper"][data-mv="1"]')
    if pg.eval_on_selector_all("#apps .app", "els=>els[1].dataset.app") != "pca-helper": issues.append("無儲存時無法調整")
    pg.close()
    b.close()
srv.shutdown()
shutil.rmtree(site)
if ext: issues.append("外部請求：" + ", ".join(sorted(set(ext))[:5]))
print("E2E OK" if not issues and not errs else f"ISSUES {len(issues)} {issues[:20]}\nERRORS {errs[:10]}")
sys.exit(1 if issues or errs else 0)
