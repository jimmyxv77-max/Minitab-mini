import io
import os
import re
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import streamlit as st

st.set_page_config(
    page_title="在线检测 SPC 与过程能力分析系统 (Minitab 风格)",
    page_icon="📈",
    layout="wide",
)


def setup_chinese_font():
  candidate_paths = [
      "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
      "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
      "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
      "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
  ]
  for path in candidate_paths:
    if os.path.exists(path):
      fm.fontManager.addfont(path)
      prop = fm.FontProperties(fname=path)
      plt.rcParams["font.sans-serif"] = [prop.get_name(), "DejaVu Sans"]
      plt.rcParams["axes.unicode_minus"] = False
      return
  available_fonts = {f.name for f in fm.fontManager.ttflist}
  for fname in [
      "Noto Sans CJK JP",
      "Noto Sans CJK SC",
      "WenQuanYi Zen Hei",
      "SimHei",
      "Microsoft YaHei",
      "Arial Unicode MS",
  ]:
    if fname in available_fonts:
      plt.rcParams["font.sans-serif"] = [fname, "DejaVu Sans"]
      plt.rcParams["axes.unicode_minus"] = False
      return
  plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
  plt.rcParams["axes.unicode_minus"] = False


setup_chinese_font()

st.title("📈 在线检测 SPC 与过程能力分析系统（Minitab 风格）")
st.caption(
    "严格对齐 Minitab「子组跨数行」CPK 算法｜统一屏蔽引擎同步驱动 CPK、箱线图与时间序列图"
)

# ==================== 1. 文件上传与 Sheet 选择 ====================
st.sidebar.header("1️⃣ 数据上传与表头识别")
uploaded_file = st.sidebar.file_uploader(
    "上传在线检测数据表 (.xlsx / .csv)", type=["xlsx", "xls", "csv"]
)

if uploaded_file is None:
  st.info(
      "👈 请在左侧边栏上传在线检测数据表格（第一行为表头，往下堆叠时间/检测数据）。"
  )
  st.stop()


@st.cache_data
def load_workbook_sheets(file_bytes, filename):
  if filename.lower().endswith(".csv"):
    df = pd.read_csv(io.BytesIO(file_bytes))
    return {"CSV_Data": df}
  xls = pd.ExcelFile(io.BytesIO(file_bytes))
  return {name: xls.parse(name) for name in xls.sheet_names}


sheets_dict = load_workbook_sheets(uploaded_file.getvalue(), uploaded_file.name)
selected_sheet = st.sidebar.selectbox(
    "选择工作表 (Sheet)", list(sheets_dict.keys())
)
df_raw = sheets_dict[selected_sheet].copy()
df_raw = df_raw.dropna(how="all").reset_index(drop=True)

if df_raw.empty:
  st.error("所选工作表无有效数据，请检查表格内容。")
  st.stop()

# 添加原始行号 (1-based)
df_raw.insert(0, "Row_Index", np.arange(1, len(df_raw) + 1))

# 自动识别数值检测列
numeric_cols_all = []
for col in df_raw.columns:
  if col == "Row_Index":
    continue
  converted = pd.to_numeric(df_raw[col], errors="coerce")
  non_null = df_raw[col].notna().sum()
  if non_null > 0 and converted.notna().sum() / non_null >= 0.3:
    df_raw[col] = converted
    numeric_cols_all.append(col)

if not numeric_cols_all:
  st.error("未识别到有效的数值型检测列，请检查表格格式（需第1行为表头）。")
  st.stop()

# ==================== 2. 检测列选择（子组跨数行） ====================
st.sidebar.header("2️⃣ 检测数据列选择（子组跨数行）")
select_all_cols = st.sidebar.checkbox("全选所有识别到的数值列", value=False)
default_cols = (
    numeric_cols_all
    if select_all_cols
    else numeric_cols_all[: min(10, len(numeric_cols_all))]
)

selected_value_cols = st.sidebar.multiselect(
    "选择参与分析的分区/通道列",
    options=numeric_cols_all,
    default=default_cols,
)

if not selected_value_cols:
  st.warning("请至少选择一列检测数值列。")
  st.stop()

# ==================== 3. 在线 SPEC 规格设定 ====================
st.sidebar.header("3️⃣ 在线 SPEC 规格设定")
col_spec1, col_spec2, col_spec3 = st.sidebar.columns(3)
lsl = col_spec1.number_input("LSL (下限)", value=157.3, format="%.4f")
target = col_spec2.number_input("Target (目标)", value=158.3, format="%.4f")
usl = col_spec3.number_input("USL (上限)", value=159.3, format="%.4f")

if lsl >= usl:
  st.sidebar.error("⚠️ LSL 必须小于 USL！")
  st.stop()

# ==================== 4. 全局统一数据屏蔽引擎（同时作用于 CPK / 箱线图 / 时间序列图） ====================
st.sidebar.header("4️⃣ 全局样本屏蔽（同步作用于全套三图）")

exclude_ranges_str = st.sidebar.text_input(
    "屏蔽指定行号区间（支持多段）",
    value="",
    placeholder="例如: 1-250, 600-630",
    help="输入要剔除的原始行号范围（1开始），多个区间用逗号隔开。屏蔽后 CPK、箱线图、时间序列图将同步使用剩余样本重新计算。",
)


def parse_exclude_indices(range_text, max_row):
  excluded = set()
  if not range_text.strip():
    return excluded
  parts = re.split(r"[,，;；\s]+", range_text.strip())
  for part in parts:
    if not part:
      continue
    if "-" in part:
      bounds = part.split("-", 1)
      try:
        start_r = max(1, int(bounds[0]))
        end_r = min(max_row, int(bounds[1]))
        if start_r <= end_r:
          excluded.update(range(start_r, end_r + 1))
      except ValueError:
        pass
    else:
      try:
        r = int(part)
        if 1 <= r <= max_row:
          excluded.add(r)
      except ValueError:
        pass
  return excluded


excluded_rows_set = parse_exclude_indices(exclude_ranges_str, len(df_raw))

filter_mode = st.sidebar.radio(
    "行均值数值筛选规则",
    options=[
        "不屏蔽（保留全部行）",
        "按 SPEC 范围过滤（行均值超出 [LSL, USL] 屏蔽）",
        "按自定义范围过滤（行均值超出设定区间屏蔽）",
    ],
    index=1,
)

row_mean = df_raw[selected_value_cols].mean(axis=1)
df_work = df_raw.copy()
df_work["_Row_Mean_"] = row_mean

# 记录每行被屏蔽的具体原因，方便导出排查
mask_not_nan = df_work["_Row_Mean_"].notna()
mask_not_in_range = ~df_work["Row_Index"].isin(excluded_rows_set)
mask_value_ok = pd.Series(True, index=df_work.index)

if filter_mode == "按 SPEC 范围过滤（行均值超出 [LSL, USL] 屏蔽）":
  mask_value_ok = (df_work["_Row_Mean_"] >= lsl) & (df_work["_Row_Mean_"] <= usl)
elif filter_mode == "按自定义范围过滤（行均值超出设定区间屏蔽）":
  c_min, c_max = st.sidebar.columns(2)
  custom_min = c_min.number_input(
      "允许行均值最小值", value=float(lsl), format="%.4f"
  )
  custom_max = c_max.number_input(
      "允许行均值最大值", value=float(usl), format="%.4f"
  )
  if custom_min >= custom_max:
    st.sidebar.error("⚠️ 自定义最小值必须小于最大值！")
    st.stop()
  mask_value_ok = (df_work["_Row_Mean_"] >= custom_min) & (
      df_work["_Row_Mean_"] <= custom_max
  )

valid_mask = mask_not_nan & mask_not_in_range & mask_value_ok

df_clean = df_work[valid_mask].copy().reset_index(drop=True)
df_removed = df_work[~valid_mask].copy().reset_index(drop=True)

# ==================== 5. 图表细节与坐标轴设置 ====================
st.sidebar.header("5️⃣ 图表细节与坐标轴设置")
show_box_outliers = st.sidebar.checkbox(
    "Box Plot 显示异常点（Outliers）", value=False
)

ts_x_mode = st.sidebar.radio(
    "时间序列图横坐标（X轴）序号",
    options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
    index=0,
)

ts_y_mode = st.sidebar.radio(
    "时间序列图纵坐标（Y轴）尺度",
    options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
    index=0,
)

# 统一从 df_clean 提取有效数据矩阵，供 CPK、箱线图、时间序列图共用
sub_matrix = df_clean[selected_value_cols].to_numpy(dtype=float)
all_valid_vals = sub_matrix[~np.isnan(sub_matrix)]

default_ymin = float(np.min(all_valid_vals)) if len(all_valid_vals) > 0 else float(lsl)
default_ymax = float(np.max(all_valid_vals)) if len(all_valid_vals) > 0 else float(usl)
pad = max((default_ymax - default_ymin) * 0.1, 0.02)

ts_ymin, ts_ymax = None, None
if ts_y_mode == "自定义范围 (Manual)":
  yc1, yc2 = st.sidebar.columns(2)
  ts_ymin = yc1.number_input(
      "Y轴最小值 (Y-Min)", value=round(default_ymin - pad, 4), format="%.4f"
  )
  ts_ymax = yc2.number_input(
      "Y轴最大值 (Y-Max)", value=round(default_ymax + pad, 4), format="%.4f"
  )
  if ts_ymin >= ts_ymax:
    st.sidebar.error("⚠️ 时间序列图 Y 轴最小值必须小于最大值！")
    st.stop()

# 顶部统一状态指标
m1, m2, m3, m4 = st.columns(4)
m1.metric("原始数据行数", len(df_work))
m2.metric("三图共用有效行数", len(df_clean))
m3.metric("已全局屏蔽行数", len(df_removed))
m4.metric("三图共用总样本数 N", len(all_valid_vals))

if len(all_valid_vals) < 2:
  st.error("过滤后有效数据点不足 2 个，无法计算标准差与过程能力，请放宽筛选条件。")
  st.stop()

# ==================== 6. Minitab「子组跨数行」核心统计计算 ====================
total_n = len(all_valid_vals)
sample_mean = float(np.mean(all_valid_vals))
std_overall = float(np.std(all_valid_vals, ddof=1))

k_cols = len(selected_value_cols)
if k_cols >= 2:
  row_counts = np.sum(~np.isnan(sub_matrix), axis=1)
  valid_sub_rows = row_counts >= 2
  if np.any(valid_sub_rows):
    sub_valid = sub_matrix[valid_sub_rows]
    r_means = np.nanmean(sub_valid, axis=1, keepdims=True)
    ss_within = np.nansum((sub_valid - r_means) ** 2)
    df_within = np.sum(row_counts[valid_sub_rows] - 1)
    std_within = float(np.sqrt(ss_within / df_within)) if df_within > 0 else std_overall
  else:
    std_within = std_overall
else:
  mr = np.abs(np.diff(all_valid_vals))
  mean_mr = float(np.mean(mr)) if len(mr) > 0 else 0.0
  std_within = mean_mr / 1.12838 if mean_mr > 0 else std_overall

cp = (usl - lsl) / (6.0 * std_within) if std_within > 0 else np.nan
cpl = (sample_mean - lsl) / (3.0 * std_within) if std_within > 0 else np.nan
cpu = (usl - sample_mean) / (3.0 * std_within) if std_within > 0 else np.nan
cpk = min(cpl, cpu)

pp = (usl - lsl) / (6.0 * std_overall) if std_overall > 0 else np.nan
ppl = (sample_mean - lsl) / (3.0 * std_overall) if std_overall > 0 else np.nan
ppu = (usl - sample_mean) / (3.0 * std_overall) if std_overall > 0 else np.nan
ppk = min(ppl, ppu)

obs_lt_lsl = float(np.sum(all_valid_vals < lsl)) / total_n * 1e6
obs_gt_usl = float(np.sum(all_valid_vals > usl)) / total_n * 1e6
obs_total = obs_lt_lsl + obs_gt_usl

exp_ov_lt_lsl = stats.norm.cdf((lsl - sample_mean) / std_overall) * 1e6 if std_overall > 0 else 0.0
exp_ov_gt_usl = (1.0 - stats.norm.cdf((usl - sample_mean) / std_overall)) * 1e6 if std_overall > 0 else 0.0
exp_ov_total = exp_ov_lt_lsl + exp_ov_gt_usl

exp_wi_lt_lsl = stats.norm.cdf((lsl - sample_mean) / std_within) * 1e6 if std_within > 0 else 0.0
exp_wi_gt_usl = (1.0 - stats.norm.cdf((usl - sample_mean) / std_within)) * 1e6 if std_within > 0 else 0.0
exp_wi_total = exp_wi_lt_lsl + exp_wi_gt_usl


# ==================== 7. 独立单张图表生成函数（全部基于 df_clean） ====================
def render_capability_plot():
  fig = plt.figure(figsize=(14, 6.2), dpi=160)
  fig.patch.set_facecolor("white")
  gs = fig.add_gridspec(1, 3, width_ratios=[1.2, 2.5, 1.1], wspace=0.14)

  ax_left = fig.add_subplot(gs[0])
  ax_mid = fig.add_subplot(gs[1])
  ax_right = fig.add_subplot(gs[2])
  ax_left.axis("off")
  ax_right.axis("off")

  bins_count = min(40, max(15, int(np.sqrt(total_n) * 0.6)))
  counts, _, _ = ax_mid.hist(
      all_valid_vals,
      bins=bins_count,
      density=True,
      color="#78A2CC",
      edgecolor="#3A5F85",
      linewidth=0.6,
      alpha=0.9,
  )

  span = usl - lsl
  x_min_c = min(lsl - 0.25 * span, float(np.min(all_valid_vals)) - 0.1 * span)
  x_max_c = max(usl + 0.25 * span, float(np.max(all_valid_vals)) + 0.1 * span)
  x_grid = np.linspace(x_min_c, x_max_c, 500)

  if std_overall > 0:
    ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, sample_mean, std_overall),
        color="#B91C1C",
        lw=1.9,
        ls="-",
        label="Overall",
    )
  if std_within > 0:
    ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, sample_mean, std_within),
        color="#374151",
        lw=1.7,
        ls="--",
        label="Within",
    )

  ax_mid.axvline(lsl, color="#DC2626", ls="--", lw=1.3)
  ax_mid.axvline(usl, color="#DC2626", ls="--", lw=1.3)
  ax_mid.axvline(target, color="#16A34A", ls=":", lw=1.2)

  y_peak = max(
      float(np.max(counts)) if len(counts) else 1.0,
      float(np.max(stats.norm.pdf(x_grid, sample_mean, std_within))) if std_within > 0 else 1.0,
  )
  ax_mid.set_ylim(0, y_peak * 1.18)
  ax_mid.set_yticks([])
  ax_mid.grid(True, axis="x", ls=":", alpha=0.45)

  ax_mid.text(lsl, y_peak * 1.20, f"LSL\n{lsl:.2f}", color="#B91C1C", ha="center", va="bottom", fontsize=9, fontweight="bold")
  ax_mid.text(usl, y_peak * 1.20, f"USL\n{usl:.2f}", color="#B91C1C", ha="center", va="bottom", fontsize=9, fontweight="bold")
  ax_mid.text(target, y_peak * 1.20, f"Target\n{target:.2f}", color="#15803D", ha="center", va="bottom", fontsize=9)
  ax_mid.legend(loc="upper right", fontsize=9, frameon=True)

  left_text = (
      f"Process Data\n"
      f"------------------------\n"
      f"LSL            {lsl:.4f}\n"
      f"Target         {target:.4f}\n"
      f"USL            {usl:.4f}\n"
      f"Sample Mean    {sample_mean:.4f}\n"
      f"Sample N       {total_n}\n"
      f"Valid Rows     {len(df_clean)}\n"
      f"Subgroup Size  {k_cols}\n"
      f"StDev(Overall) {std_overall:.6f}\n"
      f"StDev(Within)  {std_within:.6f}\n\n"
      f"Performance (PPM)\n"
      f"           Obs    Exp.Ov   Exp.Wi\n"
      f"< LSL   {obs_lt_lsl:7.2f}  {exp_ov_lt_lsl:7.2f}  {exp_wi_lt_lsl:7.2f}\n"
      f"> USL   {obs_gt_usl:7.2f}  {exp_ov_gt_usl:7.2f}  {exp_wi_gt_usl:7.2f}\n"
      f"Total   {obs_total:7.2f}  {exp_ov_total:7.2f}  {exp_wi_total:7.2f}"
  )
  ax_left.text(
      0.0, 0.5, left_text, transform=ax_left.transAxes,
      va="center", ha="left", fontsize=8.4, fontfamily="monospace",
      bbox=dict(boxstyle="round,pad=0.55", facecolor="#F8FAFC", edgecolor="#CBD5E1"),
  )

  right_text = (
      f"Overall Capability\n"
      f"--------------------\n"
      f"Pp          {pp:.2f}\n"
      f"PPL         {ppl:.2f}\n"
      f"PPU         {ppu:.2f}\n"
      f"Ppk         {ppk:.2f}\n\n"
      f"Potential (Within)\n"
      f"--------------------\n"
      f"Cp          {cp:.2f}\n"
      f"CPL         {cpl:.2f}\n"
      f"CPU         {cpu:.2f}\n"
      f"Cpk         {cpk:.2f}"
  )
  ax_right.text(
      0.02, 0.5, right_text, transform=ax_right.transAxes,
      va="center", ha="left", fontsize=9, fontfamily="monospace",
      bbox=dict(boxstyle="round,pad=0.6", facecolor="#F8FAFC", edgecolor="#CBD5E1"),
  )

  fig.suptitle(
      f"Process Capability Report — {selected_sheet} ({k_cols} Subgroups Across {len(df_clean)} Valid Rows)",
      fontsize=13.5,
      fontweight="bold",
      y=0.97,
  )
  plt.subplots_adjust(left=0.03, right=0.97, top=0.83, bottom=0.08)

  buf = io.BytesIO()
  fig.savefig(buf, format="png", dpi=160)
  buf.seek(0)
  plt.close(fig)
  return buf


def render_box_plot():
  fig, ax = plt.subplots(figsize=(14, 5.8), dpi=160)
  fig.patch.set_facecolor("white")

  box_data = [df_clean[c].dropna().to_numpy(dtype=float) for c in selected_value_cols]
  box_labels = [str(c) for c in selected_value_cols]

  ax.boxplot(
      box_data,
      tick_labels=box_labels,
      patch_artist=True,
      showfliers=show_box_outliers,
      widths=0.45,
      boxprops=dict(facecolor="#78A2CC", edgecolor="#2B4C7E", linewidth=1.0),
      medianprops=dict(color="#111827", linewidth=1.3),
      whiskerprops=dict(color="#2B4C7E", linewidth=1.0),
      capprops=dict(color="#2B4C7E", linewidth=1.0),
      flierprops=dict(marker="o", markerfacecolor="#DC2626", markeredgecolor="#DC2626", markersize=3.5),
  )

  ax.axhline(usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(lsl, color="#DC2626", ls="--", lw=1.2)

  ax_r = ax.twinx()
  ax_r.set_ylim(ax.get_ylim())
  ax_r.set_yticks([lsl, target, usl])
  ax_r.set_yticklabels([f"{lsl}", f"{target}", f"{usl}"], color="#B91C1C", fontsize=9, fontweight="bold")

  ax.set_title(
      f"Box Plot by Variable / Zone — {selected_sheet} (Valid Rows: {len(df_clean)})",
      fontsize=13.5,
      fontweight="bold",
      pad=12,
  )
  ax.set_ylabel("Value", fontsize=10.5)
  ax.tick_params(axis="x", rotation=45 if len(box_labels) > 8 else 0, labelsize=9)
  ax.grid(True, ls=":", alpha=0.45)
  plt.tight_layout()

  buf = io.BytesIO()
  fig.savefig(buf, format="png", dpi=160)
  buf.seek(0)
  plt.close(fig)
  return buf


def render_time_series_plot():
  fig, ax = plt.subplots(figsize=(14, 5.8), dpi=160)
  fig.patch.set_facecolor("white")

  if ts_x_mode == "保留原始表格行号 (Row Index)":
    x_seq = df_clean["Row_Index"].to_numpy(dtype=int)
    x_label_text = "Original Row Index"
  else:
    x_seq = np.arange(1, len(df_clean) + 1)
    x_label_text = "Filtered Sequence Index (1..N)"

  markers = ["o", "s", "D", "^", "v", "<", ">", "p", "*", "h"]
  cmap = plt.get_cmap("tab20")
  step_mark = max(1, len(x_seq) // 250)

  for idx, col_name in enumerate(selected_value_cols):
    y_col = df_clean[col_name].to_numpy(dtype=float)
    ax.plot(
        x_seq,
        y_col,
        color=cmap(idx % 20),
        lw=1.1,
        marker=markers[idx % len(markers)],
        markersize=3.4,
        markevery=step_mark,
        alpha=0.85,
        label=str(col_name),
    )

  ax.axhline(usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(lsl, color="#DC2626", ls="--", lw=1.2)

  if ts_y_mode == "自定义范围 (Manual)" and ts_ymin is not None and ts_ymax is not None:
    ax.set_ylim(ts_ymin, ts_ymax)

  ax.set_title(
      f"Time Series Plot — {selected_sheet} (Valid Rows: {len(df_clean)})",
      fontsize=13.5,
      fontweight="bold",
      pad=12,
  )
  ax.set_xlabel(x_label_text, fontsize=10.5)
  ax.set_ylabel("Value", fontsize=10.5)
  ax.grid(True, ls=":", alpha=0.45)

  handles, labels_ts = ax.get_legend_handles_labels()
  if len(handles) <= 20:
    ax.legend(handles, labels_ts, title="Variables", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8.2, title_fontsize=9)
  else:
    ax.legend(handles[:20], labels_ts[:20], title="Variables (Top 20)", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8, title_fontsize=9)

  plt.tight_layout()

  buf = io.BytesIO()
  fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
  buf.seek(0)
  plt.close(fig)
  return buf


# ==================== 8. 独立分标签页单张大图展示 ====================
tab_cap, tab_box, tab_ts, tab_data = st.tabs([
    "1️⃣ 过程能力报告 (CPK)",
    "2️⃣ 分组箱线图 (Box Plot)",
    "3️⃣ 时间序列图 (Time Series)",
    "4️⃣ 清洗后数据明细与导出",
])

with tab_cap:
  buf_cap = render_capability_plot()
  st.image(buf_cap, width="stretch")
  buf_cap.seek(0)
  st.download_button(
      "🖼️ 下载当前过程能力报告图 (.png)",
      data=buf_cap,
      file_name=f"CPK_{selected_sheet}.png",
      mime="image/png",
  )

with tab_box:
  buf_box = render_box_plot()
  st.image(buf_box, width="stretch")
  buf_box.seek(0)
  st.download_button(
      "🖼️ 下载当前箱线图 (.png)",
      data=buf_box,
      file_name=f"BoxPlot_{selected_sheet}.png",
      mime="image/png",
  )

with tab_ts:
  buf_ts = render_time_series_plot()
  st.image(buf_ts, width="stretch")
  buf_ts.seek(0)
  st.download_button(
      "🖼️ 下载当前时间序列图 (.png)",
      data=buf_ts,
      file_name=f"TimeSeries_{selected_sheet}.png",
      mime="image/png",
  )

with tab_data:
  excel_buf = io.BytesIO()
  with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
    df_clean.to_excel(writer, sheet_name="Valid_Data", index=False)
    df_removed.to_excel(writer, sheet_name="Filtered_Out_Rows", index=False)
  excel_buf.seek(0)
  st.download_button(
      "📥 导出有效数据与被屏蔽异常行 (.xlsx)",
      data=excel_buf,
      file_name=f"Filtered_{selected_sheet}.xlsx",
      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  )
  sub_t1, sub_t2 = st.tabs(["有效数据 (Valid)", "被屏蔽异常行 (Filtered Out)"])
  with sub_t1:
    st.dataframe(df_clean, width="stretch")
  with sub_t2:
    st.dataframe(df_removed, width="stretch")