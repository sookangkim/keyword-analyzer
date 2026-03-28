#!/usr/bin/env python3
"""키워드 검색량 분석기 — 웹 배포용 Flask 앱"""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# ─── 네이버 API (환경변수에서 읽음) ──────────────────────
CUSTOMER_ID = os.environ.get("NAVER_AD_CUSTOMER_ID", "")
API_LICENSE = os.environ.get("NAVER_AD_API_LICENSE", "")
API_SECRET = os.environ.get("NAVER_AD_API_SECRET", "")
BASE_URL = "https://api.searchad.naver.com"


def _sign(timestamp, method, uri):
    msg = f"{timestamp}.{method}.{uri}"
    return base64.b64encode(
        hmac.HMAC(API_SECRET.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()


def fetch_keywords(hint):
    uri = "/keywordstool"
    ts = str(int(time.time() * 1000))
    params = urllib.parse.urlencode({"hintKeywords": hint, "showDetail": "1"})
    req = urllib.request.Request(f"{BASE_URL}{uri}?{params}")
    req.add_header("X-Timestamp", ts)
    req.add_header("X-API-KEY", API_LICENSE)
    req.add_header("X-Customer", CUSTOMER_ID)
    req.add_header("X-Signature", _sign(ts, "GET", uri))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def safe_int(v):
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and "<" in v:
        return 5
    return 0


def analyze(product):
    raw = fetch_keywords(product)
    items = raw.get("keywordList", [])
    tokens = set(product.replace(" ", ""))
    results = []

    for item in items:
        kw = item["relKeyword"]
        kw_flat = kw.replace(" ", "")
        overlap = sum(1 for c in tokens if c in kw_flat)
        if overlap < 2 and product not in kw:
            continue
        pc = safe_int(item.get("monthlyPcQcCnt", 0))
        mobile = safe_int(item.get("monthlyMobileQcCnt", 0))
        total = pc + mobile
        comp = item.get("compIdx", "중간")
        results.append({"keyword": kw, "pc": pc, "mobile": mobile, "total": total, "competition": comp})

    results.sort(key=lambda x: x["total"], reverse=True)

    if len(results) >= 5:
        threshold = results[max(1, int(len(results) * 0.2))]["total"]
    elif results:
        threshold = results[0]["total"] // 2
    else:
        return results

    for kw in results:
        v, c = kw["total"], kw["competition"]
        if v >= threshold and c in ("낮음", "중간"):
            kw["grade"] = "S"
        elif v >= threshold and c == "높음":
            kw["grade"] = "A"
        elif v < threshold and c == "낮음":
            kw["grade"] = "B"
        else:
            kw["grade"] = "C"
    return results


# ─── 라우트 ────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/api/search")
def api_search():
    product = request.args.get("product", "").strip()
    if not product:
        return jsonify({"error": "상품명을 입력해주세요."})
    try:
        keywords = analyze(product)
        return jsonify({"keywords": keywords})
    except Exception as e:
        return jsonify({"error": str(e)})


# ─── HTML ──────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>키워드 검색량 분석기</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; background:#fff; color:#222; }

.header { background:#fff; padding:32px 40px 24px; border-bottom:1px solid #eee; }
.header h1 { font-size:22px; font-weight:700; color:#111; }
.header p { font-size:13px; color:#999; margin-top:4px; }
.search-bar { display:flex; gap:10px; margin-top:20px; flex-wrap:wrap; }
.search-bar input {
  flex:1; min-width:200px; max-width:420px; padding:11px 16px;
  border:1px solid #ddd; border-radius:6px; font-size:14px; outline:none;
  background:#fafafa; transition:all .2s;
}
.search-bar input:focus { border-color:#333; background:#fff; }
.search-bar button {
  padding:11px 24px; border:none; border-radius:6px;
  font-size:13px; font-weight:600; cursor:pointer; transition:all .15s;
}
.btn-search { background:#222; color:#fff; }
.btn-search:hover { background:#444; }
.btn-search:disabled { background:#bbb; cursor:wait; }
.btn-export { background:#fff; color:#222; border:1px solid #ddd !important; }
.btn-export:hover { background:#f5f5f5; }
.btn-export:disabled { color:#ccc; border-color:#eee !important; cursor:default; }

.summary { display:flex; gap:12px; padding:16px 40px; background:#fafafa; border-bottom:1px solid #eee; flex-wrap:wrap; }
.stat-card { background:#fff; border:1px solid #eee; border-radius:8px; padding:14px 22px; min-width:120px; text-align:center; }
.stat-card .num { font-size:20px; font-weight:800; color:#111; }
.stat-card .label { font-size:11px; color:#999; margin-top:3px; }

.content { padding:24px 40px; }
.legend { margin-bottom:14px; font-size:12px; color:#888; display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.legend span { display:inline-block; padding:3px 10px; border-radius:4px; font-weight:600; font-size:11px; }

.grade-S { background:#f0faf0; color:#1a8a1a; }
.grade-A { background:#f0f5ff; color:#2563eb; }
.grade-B { background:#fffbf0; color:#c77800; }
.grade-C { background:#f7f7f7; color:#999; }
.comp-high { color:#dc2626; }
.comp-mid { color:#d97706; }
.comp-low { color:#16a34a; }

table { width:100%; border-collapse:collapse; background:#fff; }
thead th {
  background:#fafafa; color:#555; padding:11px 16px;
  font-size:12px; font-weight:600; text-align:center;
  border-bottom:2px solid #eee; cursor:pointer; user-select:none;
  letter-spacing:0.5px; white-space:nowrap;
}
thead th:hover { color:#111; }
tbody td { padding:10px 16px; border-bottom:1px solid #f5f5f5; font-size:13px; color:#333; }
tbody tr:hover { background:#fafafa; }
tbody tr.row-S { border-left:3px solid #16a34a; }
tbody tr.row-A { border-left:3px solid #2563eb; }
tbody tr.row-B { border-left:3px solid #d97706; }
tbody tr.row-C { border-left:3px solid #e5e5e5; }
.col-grade { text-align:center; font-weight:700; width:55px; font-size:12px; }
.col-keyword { text-align:left; min-width:180px; font-weight:500; }
.col-num { text-align:right; font-variant-numeric:tabular-nums; }
.col-comp { text-align:center; font-weight:600; font-size:12px; }
.loading { text-align:center; padding:60px; color:#aaa; font-size:14px; }
.empty { text-align:center; padding:60px; color:#ccc; font-size:14px; }
.note { font-size:11px; color:#bbb; margin-top:16px; }

@media(max-width:768px){
  .header,.summary,.content { padding-left:16px; padding-right:16px; }
  .search-bar input { max-width:100%; }
  .stat-card { min-width:90px; padding:10px 14px; }
  .stat-card .num { font-size:16px; }
}
</style>
</head>
<body>
<div class="header">
  <h1>키워드 검색량 분석기</h1>
  <p>판매할 상품명을 입력하면 연관 키워드별 PC / 모바일 검색량과 경쟁강도를 분석합니다</p>
  <div class="search-bar">
    <input type="text" id="product" placeholder="상품명 입력 (예: 무선이어폰)" autofocus>
    <button class="btn-search" id="searchBtn" onclick="doSearch()">분석 시작</button>
    <button class="btn-export" id="exportBtn" onclick="doExport()" disabled>CSV 저장</button>
  </div>
</div>
<div class="summary" id="summary" style="display:none;"></div>
<div class="content">
  <div class="legend">
    <span class="grade-S">S 즉시공략</span>
    <span class="grade-A">A 장기투자</span>
    <span class="grade-B">B 틈새공략</span>
    <span class="grade-C">C 후순위</span>
    <span style="color:#ccc; margin:0 4px;">|</span>
    <span style="padding:0;">경쟁강도(네이버 검색광고 기준):</span>
    <span class="comp-low" style="background:none;">낮음</span>
    <span class="comp-mid" style="background:none;">중간</span>
    <span class="comp-high" style="background:none;">높음</span>
  </div>
  <div id="result"><div class="empty">상품명을 입력하고 [분석 시작]을 클릭하세요</div></div>
  <div class="note">* 경쟁강도는 네이버 검색광고 API에서 제공하는 광고 입찰 경쟁 수준입니다 | 등급은 검색량 + 경쟁강도를 조합하여 자체 분류합니다</div>
</div>

<script>
let currentData = [];
let sortCol = null, sortAsc = true;

document.getElementById('product').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});

async function doSearch() {
  const product = document.getElementById('product').value.trim();
  if (!product) return alert('상품명을 입력해주세요.');
  const btn = document.getElementById('searchBtn');
  btn.disabled = true; btn.textContent = '조회 중...';
  document.getElementById('result').innerHTML = '<div class="loading">키워드 조회 중...</div>';
  document.getElementById('summary').style.display = 'none';
  try {
    const res = await fetch('/api/search?product=' + encodeURIComponent(product));
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    currentData = data.keywords;
    renderTable(currentData);
    renderSummary(data.keywords, product);
    document.getElementById('exportBtn').disabled = false;
  } catch(e) {
    document.getElementById('result').innerHTML = '<div class="empty">오류: ' + e.message + '</div>';
  }
  btn.disabled = false; btn.textContent = '분석 시작';
}

function renderSummary(keywords, product) {
  const totalPc = keywords.reduce((s,k) => s+k.pc, 0);
  const totalMobile = keywords.reduce((s,k) => s+k.mobile, 0);
  const sCount = keywords.filter(k=>k.grade==='S').length;
  const aCount = keywords.filter(k=>k.grade==='A').length;
  const bCount = keywords.filter(k=>k.grade==='B').length;
  const el = document.getElementById('summary');
  el.style.display = 'flex';
  el.innerHTML = `
    <div class="stat-card"><div class="num">${keywords.length}</div><div class="label">총 키워드</div></div>
    <div class="stat-card"><div class="num">${totalPc.toLocaleString()}</div><div class="label">PC 검색량</div></div>
    <div class="stat-card"><div class="num">${totalMobile.toLocaleString()}</div><div class="label">모바일 검색량</div></div>
    <div class="stat-card"><div class="num">${(totalPc+totalMobile).toLocaleString()}</div><div class="label">전체 합계</div></div>
    <div class="stat-card"><div class="num" style="color:#16a34a">${sCount}</div><div class="label">S등급</div></div>
    <div class="stat-card"><div class="num" style="color:#2563eb">${aCount}</div><div class="label">A등급</div></div>
    <div class="stat-card"><div class="num" style="color:#d97706">${bCount}</div><div class="label">B등급</div></div>
  `;
}

function renderTable(data) {
  if (!data.length) { document.getElementById('result').innerHTML='<div class="empty">결과 없음</div>'; return; }
  const compClass = c => c==='높음'?'comp-high':c==='중간'?'comp-mid':'comp-low';
  let html = `<table><thead><tr>
    <th onclick="sortBy('grade')">등급</th>
    <th onclick="sortBy('keyword')">키워드</th>
    <th onclick="sortBy('pc')">PC 검색량</th>
    <th onclick="sortBy('mobile')">모바일 검색량</th>
    <th onclick="sortBy('total')">합계</th>
    <th onclick="sortBy('competition')">경쟁강도</th>
    <th onclick="sortBy('mobile_pct')">모바일비중</th>
  </tr></thead><tbody>`;
  for (const k of data) {
    const pct = k.total > 0 ? (k.mobile/k.total*100).toFixed(1)+'%' : '0%';
    html += `<tr class="row-${k.grade}">
      <td class="col-grade grade-${k.grade}">${k.grade}</td>
      <td class="col-keyword">${k.keyword}</td>
      <td class="col-num">${k.pc.toLocaleString()}</td>
      <td class="col-num">${k.mobile.toLocaleString()}</td>
      <td class="col-num"><strong>${k.total.toLocaleString()}</strong></td>
      <td class="col-comp ${compClass(k.competition)}">${k.competition}</td>
      <td class="col-num">${pct}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('result').innerHTML = html;
}

function sortBy(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = col==='keyword'; }
  const arr = [...currentData];
  arr.sort((a,b) => {
    let va = col==='mobile_pct' ? (a.total>0?a.mobile/a.total:0) : a[col];
    let vb = col==='mobile_pct' ? (b.total>0?b.mobile/b.total:0) : b[col];
    if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortAsc ? va-vb : vb-va;
  });
  renderTable(arr);
}

function doExport() {
  if (!currentData.length) return;
  const product = document.getElementById('product').value.trim();
  let csv = '\\uFEFF등급,키워드,PC검색량,모바일검색량,합계,경쟁강도,모바일비중(%)\\n';
  for (const k of currentData) {
    const pct = k.total > 0 ? (k.mobile/k.total*100).toFixed(1) : '0';
    csv += `${k.grade},${k.keyword},${k.pc},${k.mobile},${k.total},${k.competition},${pct}\\n`;
  }
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  const d = new Date().toISOString().slice(0,10).replace(/-/g,'');
  a.download = d + '_' + product + '_키워드분석.csv';
  a.click();
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8877))
    app.run(host="0.0.0.0", port=port)
