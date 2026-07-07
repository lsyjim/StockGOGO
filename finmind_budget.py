"""
finmind_budget.py — 全專案共用的 FinMind 額度守門（build_prompt_09 任務1/5）

問題：chip / revenue / 其他 dataset 各自打 FinMind，各自為政疊加會超過免費額度
（600 req/hr）→ 402/429 → 籌碼大量缺洞。

本模組提供單一 token bucket + 冷卻旗標，所有 FinMind 呼叫入口共用：
  - before_request()：達 budget 或冷卻中 → 回 False（呼叫端應改走官方備援，不發請求）
  - note_success() / note_rate_limited()：記帳與觸發冷卻
  - is_cooling() / cooldown_remaining()

語意鐵律：本模組只管「要不要發請求」；缺洞的 None 語意由呼叫端維持不變。
執行緒安全（批次掃描為多執行緒）。
"""

from __future__ import annotations

import time
import threading

try:
    from config import QuantConfig as _QC
    _COOLDOWN = _QC.FINMIND_COOLDOWN_SEC
    _BUDGET = _QC.FINMIND_HOURLY_BUDGET
except Exception:
    _COOLDOWN = 3600
    _BUDGET = 550

_lock = threading.Lock()
_req_times = []                 # 最近 3600 秒的請求時間戳
_cooldown_until = 0.0


def _prune(now):
    global _req_times
    cutoff = now - 3600
    _req_times = [t for t in _req_times if t >= cutoff]


def is_cooling() -> bool:
    with _lock:
        return time.time() < _cooldown_until


def cooldown_remaining() -> int:
    with _lock:
        return max(0, int(_cooldown_until - time.time()))


def before_request() -> bool:
    """可否發 FinMind 請求？冷卻中或達額度 → False（呼叫端走備援）。True 時已記帳。"""
    global _cooldown_until
    with _lock:
        now = time.time()
        if now < _cooldown_until:
            return False
        _prune(now)
        if len(_req_times) >= _BUDGET:
            # 主動進入冷卻，避免撞牆
            _cooldown_until = now + _COOLDOWN
            print(f"[FinMind額度] 已達每小時上限 {_BUDGET}，主動冷卻 {_COOLDOWN}s")
            return False
        _req_times.append(now)     # 樂觀記帳（發送前）
        return True


def note_rate_limited():
    """收到 402/429：進入冷卻。"""
    global _cooldown_until
    with _lock:
        _cooldown_until = time.time() + _COOLDOWN
        print(f"[FinMind額度] 偵測限流 → 冷卻 {_COOLDOWN}s")


def note_success():
    """請求成功（保留擴充；目前記帳已在 before_request 完成）。"""
    pass


def reset():
    """測試用：清空狀態。"""
    global _req_times, _cooldown_until
    with _lock:
        _req_times = []
        _cooldown_until = 0.0
