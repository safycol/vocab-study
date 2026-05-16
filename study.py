#!/usr/bin/env python3
"""Daily vocabulary study script — generates an interactive HTML study page."""

import json
import os
import random
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
VOCAB_FILE = SCRIPT_DIR / "vocab.json"
PROGRESS_FILE = SCRIPT_DIR / "progress.json"
HTML_FILE = SCRIPT_DIR / "index.html"
BATCH_SIZE = 4          # Cards shown at once
DAILY_POOL_SIZE = 20    # Max words available per day (via "次を見る")

# CI環境 or --no-browser フラグのときはブラウザを開かない
NO_BROWSER = "--no-browser" in sys.argv or os.environ.get("CI") == "true"


def load_json(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def calculate_streak(history):
    if not history:
        return 0
    today = date.today()
    dates = sorted([date.fromisoformat(h["date"]) for h in history], reverse=True)
    if dates[0] < today and (today - dates[0]).days > 1:
        return 0  # Streak broken
    streak = 1
    for i in range(1, len(dates)):
        delta = (dates[i - 1] - dates[i]).days
        if delta == 1:
            streak += 1
        elif delta > 1:
            break
    return streak


def get_today_pool(vocab, progress, today_str):
    """Return ordered list of word IDs for today's study pool."""
    # Check if today's pool already exists
    existing = next((h for h in progress["history"] if h["date"] == today_str), None)
    if existing:
        return existing["pool"]

    # Build pool from words not yet introduced
    introduced = set()
    for h in progress["history"]:
        introduced.update(h.get("pool", []))

    remaining = [w for w in vocab if w["id"] not in introduced]
    if not remaining:
        # All words introduced — start over
        remaining = vocab[:]

    random.shuffle(remaining)
    pool = [w["id"] for w in remaining[:DAILY_POOL_SIZE]]

    # Save to history
    progress["history"].append({"date": today_str, "pool": pool})
    return pool


def generate_html(vocab, today_pool, streak, total_introduced, total_words, today_str):
    """Generate the full interactive HTML study page."""
    d = datetime.strptime(today_str, "%Y-%m-%d")
    today_display = f"{d.year}年{d.month}月{d.day}日"

    # Build vocab JS object (all words keyed by ID)
    vocab_dict = {str(w["id"]): w for w in vocab}
    vocab_js = json.dumps(vocab_dict, ensure_ascii=False)
    pool_js = json.dumps(today_pool, ensure_ascii=False)
    progress_pct = int((total_introduced / total_words) * 100) if total_words else 0

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>語句学習</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --accent: #5b6ef5;
      --accent-light: #eef0fe;
      --accent-dark: #4454d4;
      --review-color: #f5a623;
      --review-light: #fff8ec;
      --done-color: #38a169;
      --text-main: #1a202c;
      --text-sub: #718096;
      --border: #e2e8f0;
      --bg: #f7f8fc;
      --card-bg: #ffffff;
      --radius: 14px;
    }}

    body {{
      font-family: -apple-system, 'Hiragino Sans', 'Yu Gothic UI', 'Meiryo', sans-serif;
      background: var(--bg);
      color: var(--text-main);
      min-height: 100vh;
    }}

    /* ── Header ─────────────────────────────────── */
    .header {{
      background: linear-gradient(135deg, #5b6ef5 0%, #7c3aed 100%);
      color: white;
      padding: 20px 20px 0;
    }}
    .header-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }}
    .header-title {{ font-size: 18px; font-weight: 700; }}
    .header-date {{ font-size: 12px; opacity: 0.85; margin-top: 2px; }}
    .streak-box {{
      text-align: center;
      background: rgba(255,255,255,0.2);
      border-radius: 10px;
      padding: 8px 14px;
      min-width: 60px;
    }}
    .streak-num {{ font-size: 22px; font-weight: 800; line-height: 1; }}
    .streak-label {{ font-size: 10px; opacity: 0.9; margin-top: 2px; }}
    .progress-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 16px;
    }}
    .progress-bar {{
      flex: 1;
      background: rgba(255,255,255,0.3);
      border-radius: 6px;
      height: 6px;
      overflow: hidden;
    }}
    .progress-fill {{
      background: white;
      height: 100%;
      border-radius: 6px;
      width: {progress_pct}%;
    }}
    .progress-text {{ font-size: 12px; opacity: 0.9; white-space: nowrap; }}

    /* ── Tabs ────────────────────────────────────── */
    .tabs {{
      display: flex;
      gap: 4px;
    }}
    .tab-btn {{
      flex: 1;
      background: transparent;
      border: none;
      color: rgba(255,255,255,0.7);
      font-size: 14px;
      font-weight: 600;
      padding: 10px 4px;
      cursor: pointer;
      position: relative;
      transition: color 0.2s;
    }}
    .tab-btn.active {{
      color: white;
    }}
    .tab-btn.active::after {{
      content: '';
      position: absolute;
      bottom: 0; left: 0; right: 0;
      height: 3px;
      background: white;
      border-radius: 3px 3px 0 0;
    }}
    .tab-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--review-color);
      color: white;
      font-size: 10px;
      font-weight: 700;
      border-radius: 10px;
      min-width: 18px;
      height: 18px;
      padding: 0 5px;
      margin-left: 5px;
      vertical-align: middle;
    }}

    /* ── Views ───────────────────────────────────── */
    .view {{ display: none; padding: 16px; }}
    .view.active {{ display: block; }}

    /* ── Cards ───────────────────────────────────── */
    .card {{
      background: var(--card-bg);
      border-radius: var(--radius);
      padding: 20px;
      margin-bottom: 12px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      border: 1.5px solid transparent;
      transition: border-color 0.2s, transform 0.15s;
      animation: slideIn 0.3s ease both;
    }}
    .card.review-marked {{
      border-color: var(--review-color);
      background: var(--review-light);
    }}
    @keyframes slideIn {{
      from {{ opacity: 0; transform: translateY(10px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes fadeOut {{
      from {{ opacity: 1; transform: translateY(0); }}
      to   {{ opacity: 0; transform: translateY(-8px); }}
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .word-block {{ flex: 1; }}
    .word {{ font-size: 26px; font-weight: 800; color: var(--text-main); }}
    .reading {{ font-size: 13px; color: var(--text-sub); margin-top: 3px; }}
    .category-tag {{
      font-size: 10px;
      font-weight: 600;
      color: var(--accent);
      background: var(--accent-light);
      padding: 3px 8px;
      border-radius: 20px;
      white-space: nowrap;
      margin-top: 4px;
    }}
    .review-btn {{
      background: none;
      border: 1.5px solid var(--border);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-sub);
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.18s;
      flex-shrink: 0;
    }}
    .review-btn:hover {{ border-color: var(--review-color); color: var(--review-color); }}
    .review-btn.marked {{
      background: var(--review-color);
      border-color: var(--review-color);
      color: white;
    }}
    .meaning {{
      font-size: 15px;
      font-weight: 600;
      color: var(--text-main);
      background: #f7f8fc;
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 12px;
      line-height: 1.6;
    }}
    .card.review-marked .meaning {{ background: rgba(255,255,255,0.7); }}
    .example-label {{
      font-size: 10px;
      font-weight: 700;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 5px;
    }}
    .example {{
      font-size: 13px;
      color: #4a5568;
      line-height: 1.7;
    }}

    /* ── Next batch button ───────────────────────── */
    .next-btn-wrap {{ text-align: center; padding: 8px 0 24px; }}
    .next-btn {{
      background: white;
      border: 1.5px solid var(--accent);
      color: var(--accent);
      font-size: 14px;
      font-weight: 700;
      padding: 12px 28px;
      border-radius: 30px;
      cursor: pointer;
      transition: all 0.18s;
    }}
    .next-btn:hover {{
      background: var(--accent);
      color: white;
    }}
    .next-btn:disabled {{
      border-color: var(--border);
      color: var(--text-sub);
      cursor: default;
    }}
    .next-btn:disabled:hover {{
      background: white;
      color: var(--text-sub);
    }}
    .pool-status {{
      text-align: center;
      font-size: 12px;
      color: var(--text-sub);
      margin-top: 10px;
      margin-bottom: 8px;
    }}

    /* ── Review list ─────────────────────────────── */
    .review-empty {{
      text-align: center;
      padding: 60px 20px;
      color: var(--text-sub);
    }}
    .review-empty .icon {{ font-size: 48px; margin-bottom: 12px; }}
    .review-empty p {{ font-size: 14px; line-height: 1.6; }}
    .review-card {{
      background: var(--card-bg);
      border-radius: var(--radius);
      padding: 18px 20px;
      margin-bottom: 12px;
      border-left: 4px solid var(--review-color);
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      animation: slideIn 0.3s ease both;
    }}
    .review-card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .review-word {{ font-size: 22px; font-weight: 800; }}
    .review-reading {{ font-size: 12px; color: var(--text-sub); margin-top: 2px; }}
    .done-btn {{
      background: white;
      border: 1.5px solid var(--done-color);
      color: var(--done-color);
      font-size: 12px;
      font-weight: 700;
      padding: 6px 12px;
      border-radius: 8px;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.18s;
      flex-shrink: 0;
    }}
    .done-btn:hover {{ background: var(--done-color); color: white; }}
    .review-meaning {{
      font-size: 14px;
      font-weight: 600;
      color: var(--text-main);
      margin-bottom: 8px;
      line-height: 1.6;
    }}
    .review-example {{ font-size: 12px; color: #4a5568; line-height: 1.7; }}
    .review-category {{
      font-size: 10px;
      font-weight: 600;
      color: var(--accent);
      background: var(--accent-light);
      padding: 2px 7px;
      border-radius: 10px;
      display: inline-block;
      margin-top: 8px;
    }}
    .review-count {{
      font-size: 12px;
      color: var(--text-sub);
      margin-bottom: 16px;
      font-weight: 600;
    }}
  </style>
</head>
<body>

<div class="header">
  <div class="header-top">
    <div>
      <div class="header-title">語句学習</div>
      <div class="header-date">{today_display}</div>
    </div>
    <div class="streak-box">
      <div class="streak-num">{streak}</div>
      <div class="streak-label">日連続</div>
    </div>
  </div>
  <div class="progress-row">
    <div class="progress-bar"><div class="progress-fill"></div></div>
    <div class="progress-text">{total_introduced}/{total_words}語 紹介済み</div>
  </div>
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('today')">今日の語句</button>
    <button class="tab-btn" onclick="switchTab('review')" id="review-tab-btn">
      復習リスト<span class="tab-badge" id="review-badge" style="display:none">0</span>
    </button>
  </div>
</div>

<div id="today-view" class="view active">
  <div id="cards-container"></div>
  <div class="pool-status" id="pool-status"></div>
  <div class="next-btn-wrap">
    <button class="next-btn" id="next-btn" onclick="showNextBatch()">次の語句を見る →</button>
  </div>
</div>

<div id="review-view" class="view">
  <div id="review-container"></div>
</div>

<script>
// ── Embedded data ────────────────────────────────────────────────
const ALL_VOCAB = {vocab_js};
const TODAY_POOL = {pool_js};
const TODAY_DATE = '{today_str}';
const BATCH_SIZE = {BATCH_SIZE};

// ── LocalStorage keys ────────────────────────────────────────────
const KEY_REVIEW   = 'kojivocab_review_v1';
const KEY_SHOWN    = 'kojivocab_shown_v1';
const KEY_DATE     = 'kojivocab_date_v1';

// ── State ────────────────────────────────────────────────────────
function getReviewSet() {{
  return new Set(JSON.parse(localStorage.getItem(KEY_REVIEW) || '[]'));
}}
function saveReviewSet(set) {{
  localStorage.setItem(KEY_REVIEW, JSON.stringify([...set]));
}}
function getShownCount() {{
  if (localStorage.getItem(KEY_DATE) !== TODAY_DATE) {{
    localStorage.setItem(KEY_DATE, TODAY_DATE);
    localStorage.setItem(KEY_SHOWN, '0');
    return 0;
  }}
  return parseInt(localStorage.getItem(KEY_SHOWN) || '0');
}}
function setShownCount(n) {{
  localStorage.setItem(KEY_SHOWN, String(n));
}}

// ── Tab switching ────────────────────────────────────────────────
function switchTab(tab) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  if (tab === 'today') {{
    document.querySelectorAll('.tab-btn')[0].classList.add('active');
    document.getElementById('today-view').classList.add('active');
  }} else {{
    document.querySelectorAll('.tab-btn')[1].classList.add('active');
    document.getElementById('review-view').classList.add('active');
    renderReviewList();
  }}
}}

// ── Review badge ─────────────────────────────────────────────────
function updateBadge() {{
  const count = getReviewSet().size;
  const badge = document.getElementById('review-badge');
  if (count > 0) {{
    badge.textContent = count;
    badge.style.display = 'inline-flex';
  }} else {{
    badge.style.display = 'none';
  }}
}}

// ── Card rendering ────────────────────────────────────────────────
function createCard(id) {{
  const w = ALL_VOCAB[String(id)];
  if (!w) return null;
  const reviewSet = getReviewSet();
  const isMarked = reviewSet.has(id);

  const card = document.createElement('div');
  card.className = 'card' + (isMarked ? ' review-marked' : '');
  card.id = 'card-' + id;

  card.innerHTML = `
    <div class="card-header">
      <div class="word-block">
        <div class="word">${{w.word}}</div>
        <div class="reading">${{w.reading}}</div>
        <div class="category-tag">${{w.category}}</div>
      </div>
      <button class="review-btn ${{isMarked ? 'marked' : ''}}"
              id="rbtn-${{id}}"
              onclick="toggleReview(${{id}})">
        ${{isMarked ? '📌 復習中' : '＋ 要復習'}}
      </button>
    </div>
    <div class="meaning">${{w.meaning}}</div>
    <div class="example-label">使用例</div>
    <div class="example">${{w.example}}</div>
  `;
  return card;
}}

function toggleReview(id) {{
  const reviewSet = getReviewSet();
  const btn = document.getElementById('rbtn-' + id);
  const card = document.getElementById('card-' + id);
  if (reviewSet.has(id)) {{
    reviewSet.delete(id);
    btn.className = 'review-btn';
    btn.textContent = '＋ 要復習';
    card.classList.remove('review-marked');
  }} else {{
    reviewSet.add(id);
    btn.className = 'review-btn marked';
    btn.textContent = '📌 復習中';
    card.classList.add('review-marked');
  }}
  saveReviewSet(reviewSet);
  updateBadge();
}}

// ── Batch display ─────────────────────────────────────────────────
let shownCount = 0;

function showNextBatch() {{
  const batch = TODAY_POOL.slice(shownCount, shownCount + BATCH_SIZE);
  if (batch.length === 0) return;

  const container = document.getElementById('cards-container');
  batch.forEach((id, i) => {{
    const card = createCard(id);
    if (card) {{
      card.style.animationDelay = (i * 0.07) + 's';
      container.appendChild(card);
    }}
  }});

  shownCount += batch.length;
  setShownCount(shownCount);
  updatePoolStatus();
}}

function updatePoolStatus() {{
  const remaining = TODAY_POOL.length - shownCount;
  const statusEl = document.getElementById('pool-status');
  const nextBtn = document.getElementById('next-btn');

  if (shownCount > 0) {{
    statusEl.textContent = `本日の語句: ${{shownCount}} / ${{TODAY_POOL.length}} 語 表示済み`;
  }}

  if (remaining <= 0) {{
    nextBtn.disabled = true;
    nextBtn.textContent = '本日分はすべて表示しました';
    statusEl.textContent = `本日の語句: ${{TODAY_POOL.length}} / ${{TODAY_POOL.length}} 語 — 明日も続けましょう！`;
  }} else {{
    nextBtn.textContent = `次の語句を見る (${{Math.min(BATCH_SIZE, remaining)}}語) →`;
  }}
}}

// ── Review list ───────────────────────────────────────────────────
function renderReviewList() {{
  const container = document.getElementById('review-container');
  container.innerHTML = '';
  const reviewSet = getReviewSet();

  if (reviewSet.size === 0) {{
    container.innerHTML = `
      <div class="review-empty">
        <div class="icon">📖</div>
        <p>復習リストはまだ空です。<br>語句カードの「＋ 要復習」ボタンで<br>気になった語句を追加しましょう。</p>
      </div>`;
    return;
  }}

  const countEl = document.createElement('div');
  countEl.className = 'review-count';
  countEl.textContent = `復習リスト: ${{reviewSet.size}} 語`;
  container.appendChild(countEl);

  reviewSet.forEach(id => {{
    const w = ALL_VOCAB[String(id)];
    if (!w) return;

    const card = document.createElement('div');
    card.className = 'review-card';
    card.id = 'rcard-' + id;
    card.innerHTML = `
      <div class="review-card-header">
        <div>
          <div class="review-word">${{w.word}}</div>
          <div class="review-reading">${{w.reading}}</div>
        </div>
        <button class="done-btn" onclick="markDone(${{id}})">覚えた ✓</button>
      </div>
      <div class="review-meaning">${{w.meaning}}</div>
      <div class="review-example">${{w.example}}</div>
      <div class="review-category">${{w.category}}</div>
    `;
    container.appendChild(card);
  }});
}}

function markDone(id) {{
  const card = document.getElementById('rcard-' + id);
  card.style.animation = 'fadeOut 0.3s ease forwards';
  setTimeout(() => {{
    const reviewSet = getReviewSet();
    reviewSet.delete(id);
    saveReviewSet(reviewSet);
    updateBadge();

    // Also update the main card button if visible
    const mainBtn = document.getElementById('rbtn-' + id);
    const mainCard = document.getElementById('card-' + id);
    if (mainBtn) {{
      mainBtn.className = 'review-btn';
      mainBtn.textContent = '＋ 要復習';
    }}
    if (mainCard) {{
      mainCard.classList.remove('review-marked');
    }}

    renderReviewList();
  }}, 280);
}}

// ── Init ──────────────────────────────────────────────────────────
shownCount = getShownCount();

// Restore previously shown cards on reload
if (shownCount > 0) {{
  const alreadyShown = TODAY_POOL.slice(0, shownCount);
  const container = document.getElementById('cards-container');
  alreadyShown.forEach(id => {{
    const card = createCard(id);
    if (card) container.appendChild(card);
  }});
  updatePoolStatus();
}} else {{
  // First load of the day — show first batch
  showNextBatch();
}}

updateBadge();
</script>
</body>
</html>"""


def main():
    today_str = date.today().isoformat()

    vocab = load_json(VOCAB_FILE, [])
    if not vocab:
        print("vocab.json が空か存在しません。語句データを追加してください。")
        return

    progress = load_json(PROGRESS_FILE, {"history": []})

    today_pool = get_today_pool(vocab, progress, today_str)
    save_json(PROGRESS_FILE, progress)

    # Count total introduced words across all history
    all_introduced = set()
    for h in progress["history"]:
        all_introduced.update(h.get("pool", []))

    streak = calculate_streak(progress["history"])

    html = generate_html(
        vocab=vocab,
        today_pool=today_pool,
        streak=streak,
        total_introduced=len(all_introduced),
        total_words=len(vocab),
        today_str=today_str,
    )

    HTML_FILE.write_text(html, encoding="utf-8")
    if NO_BROWSER:
        print(f"生成完了: {HTML_FILE}")
    else:
        webbrowser.open(HTML_FILE.as_uri())
        print(f"本日の語句ページを開きました: {HTML_FILE}")
    print(f"連続学習: {streak}日  本日のプール: {len(today_pool)}語  紹介済み: {len(all_introduced)}/{len(vocab)}語")


if __name__ == "__main__":
    main()
