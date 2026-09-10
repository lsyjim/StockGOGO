"""
test_cluster_bootstrap.py — fix_prompt_14 驗收條件2

驗證 day-cluster block bootstrap 在「日期高度聚集」資料上，
CI 明顯寬於 naive per-signal bootstrap（naive 低估不確定性）。

執行：python tests/test_cluster_bootstrap.py
"""
import os
import sys
import random
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyze_phase1 import bootstrap_ci, bootstrap_ci_clustered, cluster_profile, ci_verdict


def _make_clustered(n_days, per_day, day_effect_sd, noise_sd, seed=1):
    """
    合成資料：報酬 = 當日共同衝擊 + 個股雜訊。
    同一天的訊號共享 day effect → 真實獨立資訊量 ≈ 日期數，而非訊號筆數。
    """
    rng = random.Random(seed)
    rows = []
    for d in range(n_days):
        day = rng.gauss(0, day_effect_sd)          # 當日共同衝擊
        for k in range(per_day):
            rows.append({'as_of': f'2020-01-{d+1:02d}',
                         'ret_20_net': day + rng.gauss(0, noise_sd)})
    return rows


def test_1_high_cluster_widens_ci():
    """158 筆只來自 5 個日期 → cluster CI 應明顯寬於 naive。"""
    rows = _make_clustered(n_days=5, per_day=32, day_effect_sd=3.0, noise_sd=1.0)
    rows = rows[:158]
    prof = cluster_profile(rows)
    vals = [r['ret_20_net'] for r in rows]

    n_lo, n_hi, n_w = bootstrap_ci(vals)
    c_lo, c_hi, c_w = bootstrap_ci_clustered(rows, 'ret_20_net')

    print(f"[1] n={prof['n']} 日期數={prof['days']} 聚集比={prof['cluster_ratio']:.1%}")
    print(f"    naive   CI=[{n_lo}, {n_hi}] 寬度={n_w}")
    print(f"    cluster CI=[{c_lo}, {c_hi}] 寬度={c_w}")
    print(f"    寬度比 cluster/naive = {c_w/n_w:.2f}x")
    assert c_w > n_w * 1.5, f"cluster CI 未明顯變寬（{c_w} vs {n_w}）"
    print("    ✓ cluster CI 明顯較寬（naive 低估不確定性）")


def test_2_no_cluster_similar_ci():
    """每天只有 1 筆（無聚集）→ 兩者應接近。"""
    rows = _make_clustered(n_days=158, per_day=1, day_effect_sd=0.0, noise_sd=3.0, seed=2)
    prof = cluster_profile(rows)
    vals = [r['ret_20_net'] for r in rows]
    n_lo, n_hi, n_w = bootstrap_ci(vals)
    c_lo, c_hi, c_w = bootstrap_ci_clustered(rows, 'ret_20_net')
    print(f"[2] n={prof['n']} 日期數={prof['days']} 聚集比={prof['cluster_ratio']:.1%}")
    print(f"    naive 寬度={n_w} / cluster 寬度={c_w} → 比值 {c_w/n_w:.2f}x")
    assert 0.7 < c_w / n_w < 1.4, "無聚集時兩者應接近"
    print("    ✓ 無聚集時兩法一致（新函式未引入偏誤）")


def test_3_false_significance_demo():
    """
    示範假顯著：真實均值為 0，但因日期聚集，naive CI 可能不跨 0。
    以多個 seed 統計「naive 誤判顯著」與「cluster 誤判顯著」的比例。
    """
    n_false_naive = n_false_clu = trials = 0
    for s in range(30):
        rows = _make_clustered(n_days=6, per_day=26, day_effect_sd=3.0, noise_sd=1.0, seed=100 + s)
        vals = [r['ret_20_net'] for r in rows]
        nlo, nhi, _ = bootstrap_ci(vals)
        clo, chi, _ = bootstrap_ci_clustered(rows, 'ret_20_net')
        trials += 1
        if nlo > 0 or nhi < 0:
            n_false_naive += 1
        if clo > 0 or chi < 0:
            n_false_clu += 1
    print(f"[3] 真實均值≈0 的 {trials} 組高聚集資料中，判為『顯著』的比例：")
    print(f"    naive   {n_false_naive}/{trials} = {n_false_naive/trials:.0%}")
    print(f"    cluster {n_false_clu}/{trials} = {n_false_clu/trials:.0%}")
    assert n_false_clu <= n_false_naive, "cluster 應不比 naive 更常誤判"
    print("    ✓ cluster 降低（或至少不增加）假顯著率")


def test_4_ci_verdict_helper():
    assert ci_verdict(1.0, 3.0) == '顯著為正'
    assert ci_verdict(-6.0, -1.0) == '顯著為負'
    assert '跨 0' in ci_verdict(-1.0, 2.0)
    assert ci_verdict(None, None) == '—'
    print("[4] ci_verdict 判讀正確")


if __name__ == '__main__':
    test_1_high_cluster_widens_ci()
    test_2_no_cluster_similar_ci()
    test_3_false_significance_demo()
    test_4_ci_verdict_helper()
    print("\nALL CLUSTER BOOTSTRAP TESTS PASSED")
