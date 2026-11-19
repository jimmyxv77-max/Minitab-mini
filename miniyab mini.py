import io
import os
import re
import urllib.request
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


@st.cache_resource
def init_chinese_font():
  """自动检测或下载中文字体文件，彻底解决 Linux 云端图表中文方框乱码"""
  system_paths = [
      "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
      "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
      "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
      "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
      "C:/Windows/Fonts/msyh.ttc",
      "C:/Windows/Fonts/simhei.ttf",
      "/System/Library/Fonts/PingFang.ttc",
  ]
  for path in system_paths:
    if os.path.exists(path):
      return path

  font_dir = os.path.join(os.path.expanduser("~"), ".cache", "spc_fonts")
  os.makedirs(font_dir, exist_ok=True)
  local_font_path = os.path.join(font_dir, "NotoSansSC-Regular.ttf")

  if (
      not os.path.exists(local_font_path)
      or os.path.getsize(local_font_path) < 100000
  ):
    font_urls = [
        "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
        "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
        "https://raw.githubusercontent.com/StellarCN/scp_zh/master/fonts/SimHei.ttf",
    ]
    for url in font_urls:
      try:
        urllib.request.urlretrieve(url, local_font_path)
        if (
            os.path.exists(local_font_path)
            and os.path.getsize(local_font_path) > 100000
        ):
          break
      except Exception:
        continue

  if (
      os.path.exists(local_font_path)
      and os.path.getsize(local_font_path) > 100000
  ):
    return local_font_path
  return None


FONT_PATH = init_chinese_font()
if FONT_PATH:
  fm.fontManager.addfont(FONT_PATH)
  FONT_PROP = fm.FontProperties(fname=FONT_PATH)
  plt.rcParams["font.family"] = "sans-serif"
  plt.rcParams["font.sans-serif"] = [FONT_PROP.get_name(), "DejaVu Sans"]
else:
  FONT_PROP = fm.FontProperties()
  plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]

plt.rcParams["axes.unicode_minus"] = False

# ==================== 左侧边栏：仅保留核心数据与全局屏蔽设置 ====================
st.sidebar.header("1️⃣ 数据源与检测列")
uploaded_file = st.sidebar.file_uploader(
    "上传检测数据表 (.xlsx / .csv)", type=["xlsx", "xls", "csv"]
)

if uploaded_file is None:
  st.title("📈 在线检测 SPC 与过程能力分析系统（Minitab 风格）")
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
    "工作表 (Sheet)", list(sheets_dict.keys())
)
df_raw = sheets_dict[selected_sheet].copy()
df_raw = df_raw.dropna(how="all").reset_index(drop=True)

if df_raw.empty:
  st.error("所选工作表无有效数据，请检查表格内容。")
  st.stop()

df_raw.insert(0, "Row_Index", np.arange(1, len(df_raw) + 1))

# 识别所有数值列
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


def detect_spec_from_columns(df, num_cols):
  """根据表头关键字自动匹配 规格下限(LSL)、目标值(Target)、规格上限(USL)"""
  lsl_col, target_col, usl_col = None, None, None
  lsl_keywords = ["规格下限", "下限", "下公差", "lsl", "lower"]
  target_keywords = [
      "目标值",
      "目标",
      "中心值",
      "标准值",
      "target",
      "nominal",
      "center",
  ]
  usl_keywords = ["规格上限", "上限", "上公差", "usl", "upper"]

  for col in num_cols:
    col_clean = str(col).strip().lower()
    if lsl_col is None and any(k in col_clean for k in lsl_keywords):
      lsl_col = col
    elif usl_col is None and any(k in col_clean for k in usl_keywords):
      usl_col = col
    elif target_col is None and any(k in col_clean for k in target_keywords):
      target_col = col

  def extract_representative_val(col_name):
    if col_name is None:
      return None
    s = df[col_name].dropna()
    if s.empty:
      return None
    modes = s.mode()
    return float(modes.iloc[0]) if not modes.empty else float(s.iloc[0])

  detected_lsl = extract_representative_val(lsl_col)
  detected_target = extract_representative_val(target_col)
  detected_usl = extract_representative_val(usl_col)
  spec_cols_found = {c for c in [lsl_col, target_col, usl_col] if c is not None}
  return {
      "lsl": detected_lsl,
      "target": detected_target,
      "usl": detected_usl,
      "lsl_col": lsl_col,
      "target_col": target_col,
      "usl_col": usl_col,
      "spec_cols": spec_cols_found,
  }


spec_info = detect_spec_from_columns(df_raw, numeric_cols_all)
measurement_candidates = [
    c for c in numeric_cols_all if c not in spec_info["spec_cols"]
]
if not measurement_candidates:
  measurement_candidates = numeric_cols_all

select_all_cols = st.sidebar.checkbox("全选所有检测分区/通道列", value=False)
default_cols = (
    measurement_candidates
    if select_all_cols
    else measurement_candidates[: min(10, len(measurement_candidates))]
)
selected_value_cols = st.sidebar.multiselect(
    "参与分析的分区/通道列",
    options=numeric_cols_all,
    default=default_cols,
)

if not selected_value_cols:
  st.warning("请在左侧至少选择一列检测数值列。")
  st.stop()

# ==================== 2. SPEC 规格设定 ====================
st.sidebar.header("2️⃣ SPEC 规格设定")
dataset_key = f"{uploaded_file.name}::{selected_sheet}"

fallback_mid = float(
    np.nanmean(df_raw[selected_value_cols].to_numpy(dtype=float))
)
init_lsl = (
    spec_info["lsl"]
    if spec_info["lsl"] is not None
    else round(fallback_mid - 1.0, 4)
)
init_target = (
    spec_info["target"]
    if spec_info["target"] is not None
    else round(fallback_mid, 4)
)
init_usl = (
    spec_info["usl"]
    if spec_info["usl"] is not None
    else round(fallback_mid + 1.0, 4)
)

if (
    spec_info["target"] is None
    and spec_info["lsl"] is not None
    and spec_info["usl"] is not None
):
  init_target = round((spec_info["lsl"] + spec_info["usl"]) / 2.0, 4)

if st.session_state.get("active_dataset_key") != dataset_key:
  st.session_state["active_dataset_key"] = dataset_key
  st.session_state["spec_lsl_input"] = float(init_lsl)
  st.session_state["spec_target_input"] = float(init_target)
  st.session_state["spec_usl_input"] = float(init_usl)

if spec_info["spec_cols"]:
  st.sidebar.caption("✅ 已自动匹配表格 SPEC 列（可随时手动改写）")

col_spec1, col_spec2, col_spec3 = st.sidebar.columns(3)
lsl = col_spec1.number_input("LSL", key="spec_lsl_input", format="%.4f")
target = col_spec2.number_input("Target", key="spec_target_input", format="%.4f")
usl = col_spec3.number_input("USL", key="spec_usl_input", format="%.4f")

if lsl >= usl:
  st.sidebar.error("⚠️ LSL 必须小于 USL！")
  st.stop()

# ==================== 3. 全局统一数据屏蔽引擎 ====================
st.sidebar.header("3️⃣ 全局样本屏蔽")
exclude_ranges_str = st.sidebar.text_input(
    "屏蔽行号区间（支持多段）",
    value="",
    placeholder="例如: 1-250, 600-630",
    help="剔除指定原始行号范围（1开始），同步作用于全套图表与导出明细。",
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

filter_mode = st.sidebar.selectbox(
    "行均值数值筛选规则",
    options=[
        "不屏蔽（保留全部行）",
        "按 SPEC 范围过滤（超出 [LSL, USL] 屏蔽）",
        "按自定义范围过滤（超出设定区间屏蔽）",
    ],
    index=1,
)

row_mean = df_raw[selected_value_cols].mean(axis=1)
df_work = df_raw.copy()
df_work["_Row_Mean_"] = row_mean

mask_not_nan = df_work["_Row_Mean_"].notna()
mask_not_in_range = ~df_work["Row_Index"].isin(excluded_rows_set)
mask_value_ok = pd.Series(True, index=df_work.index)

if filter_mode == "按 SPEC 范围过滤（超出 [LSL, USL] 屏蔽）":
  mask_value_ok = (df_work["_Row_Mean_"] >= lsl) & (df_work["_Row_Mean_"] <= usl)
elif filter_mode == "按自定义范围过滤（超出设定区间屏蔽）":
  c_min, c_max = st.sidebar.columns(2)
  custom_min = c_min.number_input(
      "允许最小值", value=float(lsl), format="%.4f"
  )
  custom_max = c_max.number_input(
      "允许最大值", value=float(usl), format="%.4f"
  )
  if custom_min >= custom_max:
    st.sidebar.error("⚠️ 最小值必须小于最大值！")
    st.stop()
  mask_value_ok = (df_work["_Row_Mean_"] >= custom_min) & (
      df_work["_Row_Mean_"] <= custom_max
  )

valid_mask = mask_not_nan & mask_not_in_range & mask_value_ok
df_clean = df_work[valid_mask].copy().reset_index(drop=True)
df_removed = df_work[~valid_mask].copy().reset_index(drop=True)

raw_sub_matrix = df_clean[selected_value_cols].to_numpy(dtype=float)
raw_all_valid_vals = raw_sub_matrix[~np.isnan(raw_sub_matrix)]

if len(raw_all_valid_vals) < 2:
  st.error("过滤后有效数据点不足 2 个，无法计算标准差与过程能力，请放宽筛选条件。")
  st.stop()


def compute_within_std(mat, flat_vals):
  """按 Minitab 子组跨数行计算组内标准差 (Within StDev)"""
  s_ov = float(np.std(flat_vals, ddof=1))
  if mat.shape[1] >= 2:
    r_counts = np.sum(~np.isnan(mat), axis=1)
    v_rows = r_counts >= 2
    if np.any(v_rows):
      s_val = mat[v_rows]
      r_means = np.nanmean(s_val, axis=1, keepdims=True)
      ss_w = np.nansum((s_val - r_means) ** 2)
      df_w = np.sum(r_counts[v_rows] - 1)
      return float(np.sqrt(ss_w / df_w)) if df_w > 0 else s_ov
    return s_ov
  mr_arr = np.abs(np.diff(flat_vals))
  m_mr = float(np.mean(mr_arr)) if len(mr_arr) > 0 else 0.0
  return m_mr / 1.12838 if m_mr > 0 else s_ov


orig_mean = float(np.mean(raw_all_valid_vals))
orig_std_within = compute_within_std(raw_sub_matrix, raw_all_valid_vals)

# ==================== 左侧最底部（隐蔽收起）：过程波动校准 ====================
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 高级过程波动校准", expanded=False):
  enable_sigma_tuning = st.checkbox(
      "启用自定义西格玛校准（全图与导出表同步）", value=False
  )
  tuning_mode = st.radio(
      "校准方式",
      options=["直接指定目标西格玛 (σ)", "按目标 CPK 自动推算西格玛"],
      index=0,
  )
  center_align_pct = st.slider(
      "均值向 Target 居中比例 (%)",
      min_value=0,
      max_value=100,
      value=0,
      step=5,
  )
  adjusted_mean = orig_mean + (target - orig_mean) * (center_align_pct / 100.0)

  if tuning_mode == "直接指定目标西格玛 (σ)":
    default_sigma = round(max(orig_std_within * 0.7, 0.0001), 6)
    target_sigma_within = st.number_input(
        "目标组内西格玛 (Target Within σ)",
        min_value=0.000001,
        value=default_sigma,
        format="%.6f",
    )
  else:
    target_cpk_goal = st.selectbox(
        "目标 CPK 标准",
        options=[1.33, 1.50, 1.67, 2.00],
        index=0,
    )
    min_spec_dist = min(usl - adjusted_mean, adjusted_mean - lsl)
    if min_spec_dist <= 0:
      st.warning("⚠️ 当前均值超出规格限，请调高居中比例。")
      target_sigma_within = orig_std_within
    else:
      target_sigma_within = min_spec_dist / (3.0 * target_cpk_goal)
    st.caption(f"自动换算所需组内 σ ≈ `{target_sigma_within:.6f}`")

if enable_sigma_tuning and orig_std_within > 0:
  scale_ratio = target_sigma_within / orig_std_within
  for col in selected_value_cols:
    df_clean[col] = adjusted_mean + (df_clean[col] - orig_mean) * scale_ratio
  df_clean["_Row_Mean_"] = df_clean[selected_value_cols].mean(axis=1)

# 统一数据矩阵
sub_matrix = df_clean[selected_value_cols].to_numpy(dtype=float)
all_valid_vals = sub_matrix[~np.isnan(sub_matrix)]

# ==================== Minitab 核心统计计算 ====================
total_n = len(all_valid_vals)
sample_mean = float(np.mean(all_valid_vals))
std_overall = float(np.std(all_valid_vals, ddof=1))
std_within = compute_within_std(sub_matrix, all_valid_vals)
k_cols = len(selected_value_cols)

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

exp_ov_lt_lsl = (
    stats.norm.cdf((lsl - sample_mean) / std_overall) * 1e6
    if std_overall > 0
    else 0.0
)
exp_ov_gt_usl = (
    (1.0 - stats.norm.cdf((usl - sample_mean) / std_overall)) * 1e6
    if std_overall > 0
    else 0.0
)
exp_ov_total = exp_ov_lt_lsl + exp_ov_gt_usl

exp_wi_lt_lsl = (
    stats.norm.cdf((lsl - sample_mean) / std_within) * 1e6
    if std_within > 0
    else 0.0
)
exp_wi_gt_usl = (
    (1.0 - stats.norm.cdf((usl - sample_mean) / std_within)) * 1e6
    if std_within > 0
    else 0.0
)
exp_wi_total = exp_wi_lt_lsl + exp_wi_gt_usl

# ==================== 右侧主工作区：顶部概览与紧凑标题栏 ====================
st.title("📈 在线检测 SPC 与过程能力分析系统（Minitab 风格）")

m1, m2, m3, m4 = st.columns(4)
m1.metric("原始数据行数", len(df_work))
m2.metric("有效分析行数", len(df_clean))
m3.metric("已全局屏蔽行数", len(df_removed))
m4.metric("总样本数 N", len(all_valid_vals))

with st.expander("✏️ 自定义项目名称与各图表主标题（点击展开）", expanded=False):
  t_col0, t_col1, t_col2 = st.columns(3)
  base_topic_name = t_col0.text_input(
      "项目 / 检测参数名称（自动同步至各图）",
      value=selected_sheet,
      placeholder="例如: 单面面密度",
  )
  custom_title_cap = t_col1.text_input(
      "过程能力报告标题（留空自动生成）",
      value="",
      placeholder=f"{base_topic_name} — Process Capability Report",
  )
  custom_title_box = t_col2.text_input(
      "分组箱线图标题（留空自动生成）",
      value="",
      placeholder=f"{base_topic_name} — Box Plot",
  )
  t_col3, t_col4 = st.columns(2)
  custom_title_ts = t_col3.text_input(
      "多通道时间序列图标题（留空自动生成）",
      value="",
      placeholder=f"{base_topic_name} — Time Series Plot",
  )
  custom_title_mean = t_col4.text_input(
      "单行均值趋势图标题（留空自动生成）",
      value="",
      placeholder=f"{base_topic_name}均值",
  )

topic_clean = (
    base_topic_name.strip() if base_topic_name.strip() else selected_sheet
)
final_title_cap = (
    custom_title_cap.strip()
    if custom_title_cap.strip()
    else f"{topic_clean} — Process Capability Report"
)
final_title_box = (
    custom_title_box.strip()
    if custom_title_box.strip()
    else f"{topic_clean} — Box Plot"
)
final_title_ts = (
    custom_title_ts.strip()
    if custom_title_ts.strip()
    else f"{topic_clean} — Time Series Plot"
)
final_title_mean = (
    custom_title_mean.strip()
    if custom_title_mean.strip()
    else f"{topic_clean}均值"
)


# ==================== 图表渲染函数 ====================
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
      float(np.max(stats.norm.pdf(x_grid, sample_mean, std_within)))
      if std_within > 0
      else 1.0,
  )
  ax_mid.set_ylim(0, y_peak * 1.18)
  ax_mid.set_yticks([])
  ax_mid.grid(True, axis="x", ls=":", alpha=0.45)

  ax_mid.text(
      lsl,
      y_peak * 1.20,
      f"LSL\n{lsl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=9,
      fontweight="bold",
  )
  ax_mid.text(
      usl,
      y_peak * 1.20,
      f"USL\n{usl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=9,
      fontweight="bold",
  )
  ax_mid.text(
      target,
      y_peak * 1.20,
      f"Target\n{target:.2f}",
      color="#15803D",
      ha="center",
      va="bottom",
      fontsize=9,
  )
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
      0.0,
      0.5,
      left_text,
      transform=ax_left.transAxes,
      va="center",
      ha="left",
      fontsize=8.4,
      fontfamily="monospace",
      bbox=dict(
          boxstyle="round,pad=0.55", facecolor="#F8FAFC", edgecolor="#CBD5E1"
      ),
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
      0.02,
      0.5,
      right_text,
      transform=ax_right.transAxes,
      va="center",
      ha="left",
      fontsize=9,
      fontfamily="monospace",
      bbox=dict(
          boxstyle="round,pad=0.6", facecolor="#F8FAFC", edgecolor="#CBD5E1"
      ),
  )

  fig.suptitle(
      final_title_cap,
      fontsize=14,
      fontweight="bold",
      y=0.97,
      fontproperties=FONT_PROP,
  )
  plt.subplots_adjust(left=0.03, right=0.97, top=0.83, bottom=0.08)

  buf = io.BytesIO()
  fig.savefig(buf, format="png", dpi=160)
  buf.seek(0)
  plt.close(fig)
  return buf


def render_box_plot(
    show_outliers=False,
    show_median_val=True,
    show_mean_val=False,
    decimals=4,
):
  fig, ax = plt.subplots(figsize=(14.5, 5.8), dpi=160)
  fig.patch.set_facecolor("white")

  box_data = [
      df_clean[c].dropna().to_numpy(dtype=float) for c in selected_value_cols
  ]
  box_labels = [str(c) for c in selected_value_cols]
  n_boxes = len(box_data)
  box_width = 0.42 if n_boxes <= 15 else 0.36

  ax.boxplot(
      box_data,
      tick_labels=box_labels,
      patch_artist=True,
      showfliers=show_outliers,
      widths=box_width,
      boxprops=dict(facecolor="#78A2CC", edgecolor="#2B4C7E", linewidth=1.0),
      medianprops=dict(color="#111827", linewidth=1.3),
      whiskerprops=dict(color="#2B4C7E", linewidth=1.0),
      capprops=dict(color="#2B4C7E", linewidth=1.0),
      flierprops=dict(
          marker="o",
          markerfacecolor="#DC2626",
          markeredgecolor="#DC2626",
          markersize=3.5,
      ),
  )

  ax.axhline(usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(lsl, color="#DC2626", ls="--", lw=1.2)

  # 计算合适的字体大小，防止多箱体时文字重叠
  label_font_size = 8.2 if n_boxes <= 12 else (7.0 if n_boxes <= 22 else 6.0)
  x_offset = box_width * 0.54
  fmt_str = f"{{:.{decimals}f}}"

  # 若开启均值显示，绘制均值标记点
  if show_mean_val:
    means_arr = [float(np.mean(arr)) if len(arr) > 0 else np.nan for arr in box_data]
    ax.scatter(
        np.arange(1, n_boxes + 1),
        means_arr,
        color="#1D4ED8",
        edgecolor="white",
        s=24,
        zorder=5,
        label="Mean",
    )

  # 标注中位数与/或均值数值
  y_min_cur, y_max_cur = ax.get_ylim()
  y_span_cur = max(y_max_cur - y_min_cur, 1e-6)

  for idx, arr in enumerate(box_data):
    if len(arr) == 0:
      continue
    x_pos = (idx + 1) + x_offset
    med_v = float(np.median(arr))
    mean_v = float(np.mean(arr))

    if show_median_val and show_mean_val:
      # 同时显示两者时，自动拉开垂直间距防止文字重叠
      min_gap = y_span_cur * 0.032
      y_med_txt = med_v
      y_mean_txt = mean_v
      if abs(y_mean_txt - y_med_txt) < min_gap:
        if y_mean_txt >= y_med_txt:
          y_mean_txt = med_v + min_gap * 0.6
          y_med_txt = med_v - min_gap * 0.6
        else:
          y_mean_txt = med_v - min_gap * 0.6
          y_med_txt = med_v + min_gap * 0.6

      ax.text(
          x_pos,
          y_med_txt,
          f"Med:{fmt_str.format(med_v)}",
          va="center",
          ha="left",
          fontsize=label_font_size,
          color="#1F2937",
      )
      ax.text(
          x_pos,
          y_mean_txt,
          f"Avg:{fmt_str.format(mean_v)}",
          va="center",
          ha="left",
          fontsize=label_font_size,
          color="#1D4ED8",
      )
    elif show_median_val:
      ax.text(
          x_pos,
          med_v,
          fmt_str.format(med_v),
          va="center",
          ha="left",
          fontsize=label_font_size,
          color="#1F2937",
      )
    elif show_mean_val:
      ax.text(
          x_pos,
          mean_v,
          fmt_str.format(mean_v),
          va="center",
          ha="left",
          fontsize=label_font_size,
          color="#1D4ED8",
      )

  # 右侧留出余量，确保最后一个箱体右侧的数值不会被边框裁切
  if show_median_val or show_mean_val:
    ax.set_xlim(0.4, n_boxes + 0.95)

  ax_r = ax.twinx()
  ax_r.set_ylim(ax.get_ylim())
  ax_r.set_yticks([lsl, target, usl])
  ax_r.set_yticklabels(
      [f"{lsl}", f"{target}", f"{usl}"],
      color="#B91C1C",
      fontsize=9,
      fontweight="bold",
  )

  ax.set_title(
      final_title_box,
      fontsize=14,
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_ylabel("Value", fontsize=10.5)
  ax.tick_params(
      axis="x", rotation=45 if len(box_labels) > 6 else 0, labelsize=9
  )
  for lbl in ax.get_xticklabels():
    lbl.set_fontproperties(FONT_PROP)
  ax.grid(True, ls=":", alpha=0.45)
  plt.tight_layout()

  buf = io.BytesIO()
  fig.savefig(buf, format="png", dpi=160)
  buf.seek(0)
  plt.close(fig)
  return buf


def render_time_series_plot(x_mode_opt, y_mode_opt, ymin_val=None, ymax_val=None):
  fig, ax = plt.subplots(figsize=(14, 5.8), dpi=160)
  fig.patch.set_facecolor("white")

  if x_mode_opt == "保留原始表格行号 (Row Index)":
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

  if (
      y_mode_opt == "自定义范围 (Manual)"
      and ymin_val is not None
      and ymax_val is not None
      and ymin_val < ymax_val
  ):
    ax.set_ylim(ymin_val, ymax_val)

  ax.set_title(
      final_title_ts,
      fontsize=14,
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_xlabel(x_label_text, fontsize=10.5)
  ax.set_ylabel("Value", fontsize=10.5)
  ax.grid(True, ls=":", alpha=0.45)

  handles, labels_ts = ax.get_legend_handles_labels()
  if len(handles) <= 20:
    leg = ax.legend(
        handles,
        labels_ts,
        title="Variables",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        prop=FONT_PROP,
        fontsize=8.2,
    )
  else:
    leg = ax.legend(
        handles[:20],
        labels_ts[:20],
        title="Variables (Top 20)",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        prop=FONT_PROP,
        fontsize=8.0,
    )
  leg.get_title().set_fontsize(9)

  plt.tight_layout()

  buf = io.BytesIO()
  fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
  buf.seek(0)
  plt.close(fig)
  return buf


def render_excel_style_row_mean_plot(
    x_mode_opt, y_mode_opt, ymin_val=None, ymax_val=None
):
  """复刻经典 Excel 折线图风格的单行均值趋势图"""
  fig, ax = plt.subplots(figsize=(13.5, 5.6), dpi=160)
  fig.patch.set_facecolor("white")
  ax.set_facecolor("white")

  if x_mode_opt == "保留原始表格行号 (Row Index)":
    x_seq = df_clean["Row_Index"].to_numpy(dtype=int)
  else:
    x_seq = np.arange(1, len(df_clean) + 1)

  y_mean_series = df_clean["_Row_Mean_"].to_numpy(dtype=float)

  ax.plot(
      x_seq,
      np.full_like(x_seq, target, dtype=float),
      color="#4472C4",
      lw=2.6,
      label="目标值",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, usl, dtype=float),
      color="#ED7D31",
      lw=2.6,
      label="规格上限",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, lsl, dtype=float),
      color="#A5A5A5",
      lw=2.6,
      label="规格下限",
  )
  ax.plot(
      x_seq,
      y_mean_series,
      color="#FFC000",
      lw=2.3,
      label="平均值",
  )

  if (
      y_mode_opt == "自定义范围 (Manual)"
      and ymin_val is not None
      and ymax_val is not None
      and ymin_val < ymax_val
  ):
    ax.set_ylim(ymin_val, ymax_val)
  else:
    spec_span = usl - lsl
    y_low = min(
        lsl - 0.5 * spec_span, float(np.min(y_mean_series)) - 0.15 * spec_span
    )
    y_high = max(
        usl + 0.25 * spec_span, float(np.max(y_mean_series)) + 0.15 * spec_span
    )
    ax.set_ylim(y_low, y_high)

  ax.set_xlim(x_seq[0], x_seq[-1])

  if len(x_seq) > 1:
    tick_step = max(1, len(x_seq) // 27)
    tick_positions = x_seq[::tick_step]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(
        [str(v) for v in tick_positions],
        rotation=90,
        fontsize=9.5,
        color="#595959",
    )

  ax.tick_params(axis="y", labelsize=10, colors="#595959", length=0)
  ax.tick_params(axis="x", length=0, pad=5)

  ax.yaxis.grid(True, linestyle="-", linewidth=0.8, color="#D9D9D9")
  ax.xaxis.grid(False)
  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)
  ax.spines["left"].set_visible(False)
  ax.spines["bottom"].set_color("#D9D9D9")
  ax.spines["bottom"].set_linewidth(0.9)

  ax.set_title(
      final_title_mean,
      fontsize=17,
      fontweight="normal",
      color="#595959",
      pad=18,
      fontproperties=FONT_PROP,
  )

  leg = ax.legend(
      loc="upper center",
      bbox_to_anchor=(0.5, -0.14),
      ncol=4,
      frameon=False,
      prop=FONT_PROP,
      fontsize=11,
      handlelength=2.4,
      columnspacing=2.2,
  )
  for text in leg.get_texts():
    text.set_color("#595959")

  plt.tight_layout()

  buf = io.BytesIO()
  fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
  buf.seek(0)
  plt.close(fig)
  return buf


# ==================== 独立分标签页（各图设置内嵌于对应页面上方） ====================
tab_cap, tab_box, tab_ts, tab_mean, tab_data = st.tabs([
    "1️⃣ 过程能力报告 (CPK)",
    "2️⃣ 分组箱线图 (Box Plot)",
    "3️⃣ 多通道时间序列图 (Time Series)",
    "4️⃣ 单行均值趋势图 (Excel 风格)",
    "5️⃣ 清洗后数据明细与导出",
])

safe_prefix = re.sub(r'[\\/*?:"<>|]', "_", topic_clean)

with tab_cap:
  buf_cap = render_capability_plot()
  st.image(buf_cap, width="stretch")
  buf_cap.seek(0)
  st.download_button(
      "🖼️ 下载当前过程能力报告图 (.png)",
      data=buf_cap,
      file_name=f"{safe_prefix}_CPK.png",
      mime="image/png",
  )

with tab_box:
  bc1, bc2, bc3, bc4 = st.columns([1.3, 1.3, 1.4, 1.2])
  show_box_median = bc1.checkbox("显示中位数数值 (Median)", value=True)
  show_box_mean = bc2.checkbox("显示均值数值 (Mean)", value=False)
  show_box_outliers = bc3.checkbox("显示异常点 (Outliers)", value=False)
  box_decimals = bc4.selectbox(
      "数值小数位", options=[2, 3, 4, 5, 6], index=2, label_visibility="collapsed"
  )

  buf_box = render_box_plot(
      show_outliers=show_box_outliers,
      show_median_val=show_box_median,
      show_mean_val=show_box_mean,
      decimals=box_decimals,
  )
  st.image(buf_box, width="stretch")
  buf_box.seek(0)
  st.download_button(
      "🖼️ 下载当前箱线图 (.png)",
      data=buf_box,
      file_name=f"{safe_prefix}_BoxPlot.png",
      mime="image/png",
  )

with tab_ts:
  tc1, tc2, tc3, tc4 = st.columns([1.8, 1.5, 1.0, 1.0])
  ts_x_mode = tc1.selectbox(
      "X轴序号",
      options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
      index=0,
      key="ts_x_mode",
  )
  ts_y_mode = tc2.selectbox(
      "Y轴尺度",
      options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
      index=0,
      key="ts_y_mode",
  )
  default_ymin = float(np.min(all_valid_vals))
  default_ymax = float(np.max(all_valid_vals))
  pad = max((default_ymax - default_ymin) * 0.1, 0.02)

  ts_ymin, ts_ymax = None, None
  if ts_y_mode == "自定义范围 (Manual)":
    ts_ymin = tc3.number_input(
        "Y-Min", value=round(default_ymin - pad, 4), format="%.4f", key="ts_ymin"
    )
    ts_ymax = tc4.number_input(
        "Y-Max", value=round(default_ymax + pad, 4), format="%.4f", key="ts_ymax"
    )

  buf_ts = render_time_series_plot(ts_x_mode, ts_y_mode, ts_ymin, ts_ymax)
  st.image(buf_ts, width="stretch")
  buf_ts.seek(0)
  st.download_button(
      "🖼️ 下载当前多通道时间序列图 (.png)",
      data=buf_ts,
      file_name=f"{safe_prefix}_TimeSeries.png",
      mime="image/png",
  )

with tab_mean:
  mc1, mc2, mc3, mc4 = st.columns([1.8, 1.5, 1.0, 1.0])
  mean_x_mode = mc1.selectbox(
      "X轴序号",
      options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
      index=0,
      key="mean_x_mode",
  )
  mean_y_mode = mc2.selectbox(
      "Y轴尺度",
      options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
      index=0,
      key="mean_y_mode",
  )
  mean_ymin, mean_ymax = None, None
  if mean_y_mode == "自定义范围 (Manual)":
    spec_span = usl - lsl
    mean_ymin = mc3.number_input(
        "Y-Min",
        value=round(lsl - 0.5 * spec_span, 4),
        format="%.4f",
        key="mean_ymin",
    )
    mean_ymax = mc4.number_input(
        "Y-Max",
        value=round(usl + 0.25 * spec_span, 4),
        format="%.4f",
        key="mean_ymax",
    )

  buf_mean = render_excel_style_row_mean_plot(
      mean_x_mode, mean_y_mode, mean_ymin, mean_ymax
  )
  st.image(buf_mean, width="stretch")
  buf_mean.seek(0)
  st.download_button(
      "🖼️ 下载当前单行均值趋势图 (.png)",
      data=buf_mean,
      file_name=f"{safe_prefix}_RowMean_Trend.png",
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
      file_name=f"{safe_prefix}_Filtered.xlsx",
      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  )
  sub_t1, sub_t2 = st.tabs(["有效数据 (Valid)", "被屏蔽异常行 (Filtered Out)"])
  with sub_t1:
    st.dataframe(df_clean, width="stretch")
  with sub_t2:
    st.dataframe(df_removed, width="stretch")