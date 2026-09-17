"""
adjusted_concentration.py
調整後集中度（Adjusted Concentration）計算模組

用途
----
喺 CCASS 持股明細之上，計算「剔除結算所／非流通塊之後」嘅集中度指標，
避免將結算所代名人持倉當成街貨，令 Top5 / Top10 / HHI 被系統性溝淡。

設計原則（配合現有 財技分析 規則）
--------------------------------
1. 雙分母紀律：每個百分比同時以「已發行股本」「CCASS 總額」「調整後流通」三個
   分母輸出，唔准淨係報一個數。
2. 分母假象防護：所有百分比旁邊一定保留絕對股數，令合股／供股／配股造成嘅
   機械性百分比變動可以被識別。
3. 分子分母必須用同一條剔除規則（呢點就係 ccass-sentinel 兩個檔唔一致嘅地方）。
4. 唔輸出買賣訊號，只輸出分級描述，判斷留返畀人。

使用
----
    from adjusted_concentration import compute_concentration, ConcentrationConfig

    metrics = compute_concentration(holdings, issued_shares=1_234_567_890)
    print(metrics["adj_top5_pct"], metrics["adj_top5_shares"])

holdings 格式（list of dict）：
    [{"pid": "B01955", "name": "富途證券國際（香港）有限公司", "shares": 12345678}, ...]

如果來源係 Webb-site CSV 匯出，用 from_webbsite_frame() 先轉格式。

⚠️ 部署前必須做嘅一步
-------------------
EXCLUDE_IDS 預設係空。A 字頭參與者嘅實際語義（邊個係結算所、邊個係
非流通塊、邊個係港股通）必須自己去 HKEX 參與者名單核實一次，核實後
先填入 config。唔好照抄任何第三方 repo 嘅寫死清單。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

@dataclass
class ConcentrationConfig:
    """調整後集中度嘅計算設定。"""

    # 從分子同分母同時剔除嘅參與者 ID（結算所／非流通塊）。
    # 預設空 = 唔做任何調整，只出 raw 指標。核實過參與者名單先至填。
    exclude_ids: set[str] = field(default_factory=set)

    # 剔除模式：
    #   "ids"     — 只剔 exclude_ids 入面嘅 ID（內部一致，建議用呢個）
    #   "prefix"  — 剔走所有 exclude_prefixes 開頭嘅 ID
    exclude_mode: str = "ids"
    exclude_prefixes: tuple[str, ...] = ()

    # 券商（經紀）ID 前綴。用嚟分開「經紀倉」同「託管行倉」。
    broker_prefixes: tuple[str, ...] = ("B",)

    # 散戶型券商 ID：呢批倉位上升通常代表貨分散到散戶手上。
    # B01955 = 富途，係從 ccass-sentinel 原始碼讀到嘅標註，仍需自行核實。
    # 其餘（耀才、盈透、中銀、匯豐等）請自己查實 ID 後補上，唔好靠估。
    retail_broker_ids: set[str] = field(default_factory=lambda: {"B01955"})

    # 單一參與者佔調整後流通超過呢個百分比，就標記為重倉。
    heavy_holder_pct: float = 10.0

    # 判斷某參與者係咪「大到唔應該當街貨」嘅門檻（佔比）。
    dominant_pct: float = 30.0


DEFAULT_CONFIG = ConcentrationConfig()


# ---------------------------------------------------------------------------
# 內部工具
# ---------------------------------------------------------------------------

def _is_excluded(pid: str, cfg: ConcentrationConfig) -> bool:
    if cfg.exclude_mode == "prefix":
        return bool(cfg.exclude_prefixes) and pid.startswith(cfg.exclude_prefixes)
    return pid in cfg.exclude_ids


def _is_broker(pid: str, cfg: ConcentrationConfig) -> bool:
    return pid.startswith(cfg.broker_prefixes)


def _pct(part: int, whole: int) -> float | None:
    """安全百分比。分母為 0 或未知時回 None，唔回 0 — 0 同「未知」意思唔同。"""
    if not whole:
        return None
    return round(part / whole * 100, 4)


def _hhi(shares: Iterable[int], total: int) -> float | None:
    """Herfindahl-Hirschman Index，以百分比平方計，範圍 0–10000。"""
    if not total:
        return None
    return round(sum((s / total * 100) ** 2 for s in shares if s > 0), 1)


def _topn(sorted_shares: list[int], n: int) -> int:
    return sum(sorted_shares[:n])


# ---------------------------------------------------------------------------
# 主計算
# ---------------------------------------------------------------------------

def compute_concentration(
    holdings: list[dict[str, Any]],
    issued_shares: int | None = None,
    cfg: ConcentrationConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """
    計算一日快照嘅集中度指標。

    參數
    ----
    holdings      : CCASS 持股明細，每項需有 pid / name / shares
    issued_shares : 已發行股本（股數）。有就會同時輸出以已發行股本為分母嘅
                    百分比；冇就相關欄位回 None，唔會靜靜用 CCASS 總額頂替。
    cfg           : ConcentrationConfig

    回傳 dict，主要欄位：
        ccass_total_shares      CCASS 總持股（股）
        ccass_pct_of_issued     CCASS 總額 / 已發行股本
        excluded_shares         被剔除（結算所／非流通）嘅股數
        adjusted_float_shares   調整後流通 = CCASS 總額 − excluded
        raw_top5_pct / raw_top10_pct / raw_hhi        （以 CCASS 總額為分母）
        adj_top5_pct / adj_top10_pct / adj_hhi        （以調整後流通為分母）
        adj_top5_pct_of_issued / adj_top10_pct_of_issued（以已發行股本為分母）
        top5_shares / top10_shares                    （絕對股數，防分母假象）
        broker_top5_pct         經紀倉 Top5（以調整後流通為分母）
        top_holder / top_broker 最大參與者 / 最大經紀
        retail_pct              散戶型券商合計佔比
        participant_count       參與者數目
        flags                   分級標籤（見 grade_flags）
    """
    clean = [
        {"pid": str(h["pid"]).strip(), "name": str(h.get("name", "")).strip(),
         "shares": int(h["shares"])}
        for h in holdings
        if h.get("pid") is not None and int(h.get("shares") or 0) > 0
    ]
    if not clean:
        return {"error": "NO_HOLDINGS", "participant_count": 0}

    clean.sort(key=lambda x: x["shares"], reverse=True)
    ccass_total = sum(h["shares"] for h in clean)

    excluded = [h for h in clean if _is_excluded(h["pid"], cfg)]
    excluded_shares = sum(h["shares"] for h in excluded)

    # 分子同分母用同一條規則 —— 呢點係關鍵，唔可以一邊剔 A*、一邊只減 A00005
    kept = [h for h in clean if not _is_excluded(h["pid"], cfg)]
    adj_float = ccass_total - excluded_shares

    kept_shares = [h["shares"] for h in kept]
    all_shares = [h["shares"] for h in clean]

    brokers = [h for h in kept if _is_broker(h["pid"], cfg)]
    broker_shares = [h["shares"] for h in brokers]

    retail_shares = sum(h["shares"] for h in kept if h["pid"] in cfg.retail_broker_ids)

    top5_s, top10_s = _topn(kept_shares, 5), _topn(kept_shares, 10)
    top_holder = kept[0] if kept else None
    top_broker = brokers[0] if brokers else None

    out: dict[str, Any] = {
        # ---- 絕對股數（分母假象防護：任何百分比都要有得對照股數）----
        "ccass_total_shares": ccass_total,
        "issued_shares": issued_shares,
        "excluded_shares": excluded_shares,
        "excluded_ids": sorted({h["pid"] for h in excluded}),
        "adjusted_float_shares": adj_float,
        "top5_shares": top5_s,
        "top10_shares": top10_s,
        "participant_count": len(clean),

        # ---- 分母一：已發行股本 ----
        "ccass_pct_of_issued": _pct(ccass_total, issued_shares or 0),
        "adj_float_pct_of_issued": _pct(adj_float, issued_shares or 0),
        "adj_top5_pct_of_issued": _pct(top5_s, issued_shares or 0),
        "adj_top10_pct_of_issued": _pct(top10_s, issued_shares or 0),

        # ---- 分母二：CCASS 總額（未調整）----
        "raw_top5_pct": _pct(_topn(all_shares, 5), ccass_total),
        "raw_top10_pct": _pct(_topn(all_shares, 10), ccass_total),
        "raw_hhi": _hhi(all_shares, ccass_total),
        "excluded_pct_of_ccass": _pct(excluded_shares, ccass_total),

        # ---- 分母三：調整後流通 ----
        "adj_top5_pct": _pct(top5_s, adj_float),
        "adj_top10_pct": _pct(top10_s, adj_float),
        "adj_hhi": _hhi(kept_shares, adj_float),
        "broker_top5_pct": _pct(_topn(broker_shares, 5), adj_float),
        "retail_pct": _pct(retail_shares, adj_float),

        # ---- 最大倉 ----
        "top_holder_id": top_holder["pid"] if top_holder else None,
        "top_holder_name": top_holder["name"] if top_holder else None,
        "top_holder_pct": _pct(top_holder["shares"], adj_float) if top_holder else None,
        "top_holder_shares": top_holder["shares"] if top_holder else None,
        "top_broker_id": top_broker["pid"] if top_broker else None,
        "top_broker_name": top_broker["name"] if top_broker else None,
        "top_broker_pct": _pct(top_broker["shares"], adj_float) if top_broker else None,
        "top_broker_shares": top_broker["shares"] if top_broker else None,

        "config_exclude_mode": cfg.exclude_mode,
        "config_exclude_ids": sorted(cfg.exclude_ids),
    }
    out["flags"] = grade_flags(out, cfg)
    return out


def grade_flags(m: dict[str, Any], cfg: ConcentrationConfig = DEFAULT_CONFIG) -> list[str]:
    """
    輸出中文分級標籤。刻意唔出 BUY/SELL —— 集中度高唔等於一定乾，
    亦唔等於會升，判斷留返畀人。
    """
    flags: list[str] = []
    t5 = m.get("adj_top5_pct")
    if t5 is not None:
        if t5 > 95:
            flags.append("極高集中（調整後Top5>95%）")
        elif t5 > 90:
            flags.append("高集中（調整後Top5>90%）")
        elif t5 < 50:
            flags.append("街貨分散（調整後Top5<50%）")

    if (m.get("top_holder_pct") or 0) > cfg.dominant_pct:
        flags.append(f"單一參與者佔調整後流通>{cfg.dominant_pct:.0f}%")
    elif (m.get("top_broker_pct") or 0) > cfg.heavy_holder_pct:
        flags.append(f"最大經紀倉>{cfg.heavy_holder_pct:.0f}%")

    if (m.get("excluded_pct_of_ccass") or 0) > 30:
        flags.append("結算所／非流通塊佔CCASS>30%，raw指標嚴重失真")

    if (m.get("participant_count") or 0) < 80:
        flags.append("參與者數目偏少")

    if m.get("issued_shares") is None:
        flags.append("未提供已發行股本，無法計算已發行股本分母")

    return flags or ["無觸發標籤"]


# ---------------------------------------------------------------------------
# 日對日變動偵測
# ---------------------------------------------------------------------------

def detect_changes(
    today: dict[str, Any],
    prior: dict[str, Any],
    today_holdings: list[dict[str, Any]] | None = None,
    prior_holdings: list[dict[str, Any]] | None = None,
    cfg: ConcentrationConfig = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    """
    比較兩個快照，輸出觀察項（唔係買賣訊號）。

    今日 vs 上一個有數據嘅日子。today / prior 係 compute_concentration 嘅輸出。
    如果另外提供 holdings 明細，會多做「單一參與者大幅變動」偵測。

    每項觀察包含 type / level / message / evidence。
    level 用你現有嘅分級語言，唔用絕對字眼。
    """
    obs: list[dict[str, Any]] = []
    if not today or not prior or today.get("error") or prior.get("error"):
        return obs

    def _add(t: str, lvl: str, msg: str, ev: dict[str, Any]) -> None:
        obs.append({"type": t, "level": lvl, "message": msg, "evidence": ev})

    # --- 1. 經紀集中度跳升 ---
    bt_now, bt_prior = today.get("broker_top5_pct"), prior.get("broker_top5_pct")
    if bt_now is not None and bt_prior is not None:
        d = bt_now - bt_prior
        if d > 3:
            _add("BROKER_CONCENTRATION_UP", "偏似收貨或轉倉",
                 f"經紀倉Top5 一日由 {bt_prior:.1f}% 升至 {bt_now:.1f}%（{d:+.1f}pp）",
                 {"prior": bt_prior, "now": bt_now, "delta_pp": round(d, 2)})
        elif d < -3:
            _add("BROKER_CONCENTRATION_DOWN", "派貨風險上升",
                 f"經紀倉Top5 一日由 {bt_prior:.1f}% 跌至 {bt_now:.1f}%（{d:+.1f}pp）",
                 {"prior": bt_prior, "now": bt_now, "delta_pp": round(d, 2)})

    # --- 2. 參與者數目變動 ---
    pc_now, pc_prior = today.get("participant_count", 0), prior.get("participant_count", 0)
    if pc_prior:
        ratio = (pc_now - pc_prior) / pc_prior
        if ratio < -0.10:
            _add("PARTICIPANT_DROP", "偏似歸邊",
                 f"參與者數目由 {pc_prior} 減至 {pc_now}（{ratio*100:+.1f}%）",
                 {"prior": pc_prior, "now": pc_now})
        elif ratio > 0.10:
            _add("PARTICIPANT_RISE", "偏似分散",
                 f"參與者數目由 {pc_prior} 增至 {pc_now}（{ratio*100:+.1f}%）",
                 {"prior": pc_prior, "now": pc_now})

    # --- 3. 散戶型券商佔比上升 ---
    r_now, r_prior = today.get("retail_pct"), prior.get("retail_pct")
    if r_now is not None and r_prior is not None and (r_now - r_prior) > 2:
        _add("RETAIL_UP", "派貨風險上升",
             f"散戶型券商合計由 {r_prior:.1f}% 升至 {r_now:.1f}%",
             {"prior": r_prior, "now": r_now, "ids": sorted(cfg.retail_broker_ids)})

    # --- 4. CCASS 總額擴張：分開「新股上市」同「實物入冊」---
    # 呢個係 ccass-sentinel 混為一談嘅地方。有已發行股本就分得開。
    ct_now, ct_prior = today.get("ccass_total_shares", 0), prior.get("ccass_total_shares", 0)
    is_now, is_prior = today.get("issued_shares"), prior.get("issued_shares")
    if ct_prior and (ct_now - ct_prior) / ct_prior > 0.05:
        pct = (ct_now - ct_prior) / ct_prior * 100
        if is_now and is_prior and is_now > is_prior * 1.001:
            _add("CCASS_TOTAL_UP_NEW_SHARES", "已查證：股本擴大",
                 f"CCASS總額 {pct:+.1f}%，同期已發行股本亦由 {is_prior:,} 增至 {is_now:,}"
                 f"，屬新股上市／配發造成，非市場買賣",
                 {"ccass_prior": ct_prior, "ccass_now": ct_now,
                  "issued_prior": is_prior, "issued_now": is_now})
        elif is_now and is_prior:
            _add("CCASS_TOTAL_UP_DEPOSIT", "偏似實物股票存入",
                 f"CCASS總額 {pct:+.1f}% 但已發行股本不變（{is_now:,}），"
                 f"偏似場外／禁售期滿股份存入CCASS，需核對公告確認",
                 {"ccass_prior": ct_prior, "ccass_now": ct_now, "issued": is_now})
        else:
            _add("CCASS_TOTAL_UP_UNKNOWN", "未足以定性",
                 f"CCASS總額 {pct:+.1f}%，但未有已發行股本數據，"
                 f"未能分辨屬新股上市抑或實物存入",
                 {"ccass_prior": ct_prior, "ccass_now": ct_now})
    elif ct_prior and (ct_now - ct_prior) / ct_prior < -0.05:
        pct = (ct_now - ct_prior) / ct_prior * 100
        _add("CCASS_TOTAL_DOWN", "偏似提取離開CCASS",
             f"CCASS總額 {pct:+.1f}%，偏似股份被提取為實物，街貨機械性縮減",
             {"ccass_prior": ct_prior, "ccass_now": ct_now})

    # --- 5. 單一參與者大幅變動（需要明細）---
    if today_holdings and prior_holdings:
        af_now = today.get("adjusted_float_shares") or 0
        af_prior = prior.get("adjusted_float_shares") or 0
        if af_now and af_prior:
            pm = {str(h["pid"]): int(h["shares"]) for h in prior_holdings}
            tm = {str(h["pid"]): int(h["shares"]) for h in today_holdings}
            names = {str(h["pid"]): str(h.get("name", "")) for h in today_holdings}
            names.update({str(h["pid"]): str(h.get("name", "")) for h in prior_holdings})
            for pid in set(pm) | set(tm):
                if _is_excluded(pid, cfg):
                    continue
                s_now, s_prior = tm.get(pid, 0), pm.get(pid, 0)
                p_now = s_now / af_now * 100
                p_prior = s_prior / af_prior * 100
                d = p_now - p_prior
                if abs(d) >= 5:
                    lvl = "偏似收貨或轉倉" if d > 0 else "偏似減倉或轉倉"
                    _add("PARTICIPANT_SHIFT", lvl,
                         f"{pid} {names.get(pid,'')[:24]} 由 {p_prior:.1f}% 變 {p_now:.1f}%"
                         f"（{d:+.1f}pp，{s_prior:,} → {s_now:,} 股）",
                         {"pid": pid, "prior_pct": round(p_prior, 2),
                          "now_pct": round(p_now, 2), "delta_pp": round(d, 2),
                          "prior_shares": s_prior, "now_shares": s_now})

    # --- 6. 轉倉配對：一增一減、總額不變，提示唔好當市場派貨 ---
    ups = [o for o in obs if o["type"] == "PARTICIPANT_SHIFT" and o["evidence"]["delta_pp"] > 0]
    downs = [o for o in obs if o["type"] == "PARTICIPANT_SHIFT" and o["evidence"]["delta_pp"] < 0]
    for u in ups:
        for dn in downs:
            gap = abs(u["evidence"]["delta_pp"] + dn["evidence"]["delta_pp"])
            if gap < 1.0:
                _add("LIKELY_TRANSFER", "偏似轉倉",
                     f"{dn['evidence']['pid']} 減 {abs(dn['evidence']['delta_pp']):.1f}pp，"
                     f"{u['evidence']['pid']} 增 {u['evidence']['delta_pp']:.1f}pp，"
                     f"數量相若，偏似非市場轉倉而非派貨；須以同期成交額核對",
                     {"from": dn["evidence"]["pid"], "to": u["evidence"]["pid"],
                      "gap_pp": round(gap, 2)})

    return obs


# ---------------------------------------------------------------------------
# 資料來源轉接器
# ---------------------------------------------------------------------------

def from_webbsite_frame(df, section: str = "holdings") -> list[dict[str, Any]]:
    """
    將現有工具匯出嘅 Webb-site CCASS CSV（多 section 結構）轉成本模組格式。

    已知格式特性（沿用現有工具紀律）：
      pd.read_csv(path, skiprows=4, encoding="utf-8-sig")
      再 filter record_type == "data"，然後按 section 取子集。

    欄位名稱各版本有出入，所以用候選清單自動對應；對唔到就 raise，
    唔會靜靜咁用錯欄位。
    """
    d = df
    if "record_type" in d.columns:
        d = d[d["record_type"] == "data"]
    if "section" in d.columns:
        d = d[d["section"].astype(str).str.lower() == section.lower()]

    id_cands = ["participant_id", "pid", "broker_id", "id", "參與者編號", "Participant ID"]
    name_cands = ["participant_name", "name", "broker_name", "參與者名稱", "Participant Name"]
    qty_cands = ["shareholding", "shares", "holding", "quantity", "持股量", "Shareholding"]

    def pick(cands: list[str]) -> str:
        for c in cands:
            if c in d.columns:
                return c
        raise KeyError(
            f"搵唔到對應欄位。候選：{cands}；實際欄位：{list(d.columns)}。"
            f"請確認 section='{section}' 同 skiprows 設定。"
        )

    ic, nc, qc = pick(id_cands), pick(name_cands), pick(qty_cands)
    out = []
    for _, row in d.iterrows():
        raw_q = str(row[qc]).replace(",", "").strip()
        if not raw_q or raw_q.lower() in {"nan", "none", "-"}:
            continue
        try:
            shares = int(float(raw_q))
        except ValueError:
            continue
        if shares <= 0:
            continue
        out.append({"pid": str(row[ic]).strip(),
                    "name": str(row[nc]).strip(),
                    "shares": shares})
    if not out:
        raise ValueError(f"section='{section}' 解析後冇有效紀錄，請檢查來源 CSV。")
    return out


def format_report(m: dict[str, Any], observations: list[dict[str, Any]] | None = None) -> str:
    """出一段可以直接貼入分析嘅 Markdown，已分開【已查證事實】同標籤。"""
    if m.get("error"):
        return f"**CCASS 集中度**：{m['error']} — 未取得持股明細，唔作估算。"

    def f(v, suffix="%"):
        return "未知" if v is None else f"{v:.2f}{suffix}"

    lines = [
        "### 調整後集中度",
        "",
        "| 指標 | 以已發行股本 | 以CCASS總額 | 以調整後流通 | 絕對股數 |",
        "|---|---|---|---|---|",
        f"| CCASS 總額 | {f(m['ccass_pct_of_issued'])} | 100.00% | — | {m['ccass_total_shares']:,} |",
        f"| 剔除（結算所／非流通） | — | {f(m['excluded_pct_of_ccass'])} | — | {m['excluded_shares']:,} |",
        f"| 調整後流通 | {f(m['adj_float_pct_of_issued'])} | — | 100.00% | {m['adjusted_float_shares']:,} |",
        f"| Top 5 | {f(m['adj_top5_pct_of_issued'])} | {f(m['raw_top5_pct'])} | {f(m['adj_top5_pct'])} | {m['top5_shares']:,} |",
        f"| Top 10 | {f(m['adj_top10_pct_of_issued'])} | {f(m['raw_top10_pct'])} | {f(m['adj_top10_pct'])} | {m['top10_shares']:,} |",
        "",
        f"- HHI：未調整 {m['raw_hhi']} ／ 調整後 {m['adj_hhi']}（0–10000）",
        f"- 參與者數目：{m['participant_count']}",
        f"- 最大參與者：{m['top_holder_id']} {m['top_holder_name']} — "
        f"{f(m['top_holder_pct'])}（{m['top_holder_shares']:,} 股）",
        f"- 最大經紀倉：{m['top_broker_id']} {m['top_broker_name']} — "
        f"{f(m['top_broker_pct'])}（{(m['top_broker_shares'] or 0):,} 股）",
        f"- 經紀倉 Top5（剔除託管行後）：{f(m['broker_top5_pct'])}",
        f"- 散戶型券商合計：{f(m['retail_pct'])}",
        f"- 剔除規則：{m['config_exclude_mode']} / {m['config_exclude_ids'] or '（未設定，未作調整）'}",
        "",
        "**標籤**：" + "；".join(m["flags"]),
    ]

    if observations:
        lines += ["", "### 日對日觀察", ""]
        for o in observations:
            lines.append(f"- **{o['level']}** — {o['message']}")
        lines += ["", "（以上為結構觀察，須以同期成交額核對；集中度高不等於一定乾，"
                      "亦不構成投資建議。）"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 自測
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = ConcentrationConfig(exclude_ids={"A00005"})

    day1 = [
        {"pid": "A00005", "name": "結算所代名人（示例）", "shares": 400_000_000},
        {"pid": "B01234", "name": "示例券商甲", "shares": 250_000_000},
        {"pid": "B02345", "name": "示例券商乙", "shares": 120_000_000},
        {"pid": "C00019", "name": "示例託管行", "shares": 60_000_000},
        {"pid": "B01955", "name": "富途證券", "shares": 40_000_000},
        {"pid": "B03456", "name": "示例券商丙", "shares": 20_000_000},
        {"pid": "B04567", "name": "示例券商丁", "shares": 10_000_000},
    ]
    # 第二日：券商甲整塊轉去券商乙（典型轉倉），總額不變
    day2 = [
        {"pid": "A00005", "name": "結算所代名人（示例）", "shares": 400_000_000},
        {"pid": "B01234", "name": "示例券商甲", "shares": 150_000_000},
        {"pid": "B02345", "name": "示例券商乙", "shares": 220_000_000},
        {"pid": "C00019", "name": "示例託管行", "shares": 60_000_000},
        {"pid": "B01955", "name": "富途證券", "shares": 40_000_000},
        {"pid": "B03456", "name": "示例券商丙", "shares": 20_000_000},
        {"pid": "B04567", "name": "示例券商丁", "shares": 10_000_000},
    ]

    issued = 1_200_000_000
    m1 = compute_concentration(day1, issued_shares=issued, cfg=cfg)
    m2 = compute_concentration(day2, issued_shares=issued, cfg=cfg)
    obs = detect_changes(m2, m1, day2, day1, cfg=cfg)

    print(format_report(m2, obs))
    print()
    print("--- 對照：唔剔除任何嘢（raw）---")
    m_raw = compute_concentration(day2, issued_shares=issued)
    print(f"raw_top5 = {m_raw['raw_top5_pct']}%  vs  adj_top5 = {m2['adj_top5_pct']}%")
    print("差距 =", round(m2["adj_top5_pct"] - m_raw["raw_top5_pct"], 2), "pp")
