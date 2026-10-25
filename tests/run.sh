#!/bin/sh
# 入口頁測試：sh tests/run.sh [其他 app 所在的上層資料夾]
# 有給上層資料夾時，會用實際的 pca-helper、abx-helper、oncall-helper 測版本讀取
cd "$(dirname "$0")/.." || exit 1
APPS="$1"
FAIL=0
if [ -n "$APPS" ]; then
  node tests/static.js index.html "$APPS"/pca-helper/index.html "$APPS"/abx-helper/index.html "$APPS"/oncall-helper/index.html || FAIL=1
  python3 tests/e2e.py index.html "$APPS" "${SHOT:-}" || FAIL=1
else
  node tests/static.js index.html || FAIL=1
  python3 tests/e2e.py index.html || FAIL=1
fi
exit $FAIL
