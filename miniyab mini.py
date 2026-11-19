import io
import os
import re
import urllib.request
import matplotlib.font_manager as fm
from matplotlib.patches import Rectangle
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


def detect_spec_from_columns(df, all_cols):
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

  for col in all_cols:
    if col == "Row_Index":
      continue
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
    s = pd.to_numeric(df[col_name], errors="coerce").dropna()
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


spec_info = detect_spec_from_columns(df_raw, df_raw.columns)
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
  st.warning("👈 请在左侧至少选择一列检测数值列。")
  st.stop()

# ==================== 2. SPEC 规格设定（抗尖峰干扰估算） ====================
st.sidebar.header("2️⃣ SPEC 规格设定")
dataset_key = f"{uploaded_file.name}::{selected_sheet}"
cols_signature = tuple(selected_value_cols)


def compute_recommended_spec(df_src, cols_sel, s_info):
  """使用中位数与抗差标准差(MAD)估算 SPEC，避免编码器尖峰(如11205.01)带偏上下限"""
  vals = df_src[list(cols_sel)].to_numpy(dtype=float)
  valid_v = vals[~np.isnan(vals)]
  if len(valid_v) > 0:
    mid = float(np.median(valid_v))
    mad = float(np.median(np.abs(valid_v - mid)))
    robust_std = mad * 1.4826 if mad > 0 else float(np.std(valid_v, ddof=1))
    half_tol = max(round(robust_std * 4.5, 4), 0.2) if robust_std > 0 else 1.0
  else:
    mid, half_tol = 0.0, 1.0

  rec_lsl = (
      s_info["lsl"] if s_info["lsl"] is not None else round(mid - half_tol, 4)
  )
  rec_usl = (
      s_info["usl"] if s_info["usl"] is not None else round(mid + half_tol, 4)
  )
  if s_info["target"] is not None:
    rec_target = s_info["target"]
  elif s_info["lsl"] is not None and s_info["usl"] is not None:
    rec_target = round((s_info["lsl"] + s_info["usl"]) / 2.0, 4)
  else:
    rec_target = round(mid, 4)
  return float(rec_lsl), float(rec_target), float(rec_usl)


rec_lsl, rec_target, rec_usl = compute_recommended_spec(
    df_raw, selected_value_cols, spec_info
)
has_table_spec = any(
    spec_info[k] is not None for k in ("lsl", "target", "usl")
)

need_auto_fill = False
if st.session_state.get("active_dataset_key") != dataset_key:
  st.session_state["active_dataset_key"] = dataset_key
  st.session_state["spec_manually_edited"] = False
  need_auto_fill = True
elif (
    "spec_lsl_input" not in st.session_state
    or "spec_usl_input" not in st.session_state
    or st.session_state["spec_lsl_input"] >= st.session_state["spec_usl_input"]
):
  need_auto_fill = True
elif (
    not has_table_spec
    and not st.session_state.get("spec_manually_edited", False)
    and st.session_state.get("last_cols_signature") != cols_signature
):
  need_auto_fill = True

st.session_state["last_cols_signature"] = cols_signature

if need_auto_fill:
  st.session_state["spec_lsl_input"] = rec_lsl
  st.session_state["spec_target_input"] = rec_target
  st.session_state["spec_usl_input"] = rec_usl


def on_spec_manual_change():
  st.session_state["spec_manually_edited"] = True


if has_table_spec:
  st.sidebar.caption("✅ 已从表格 SPEC 列自动获取上下限")
else:
  st.sidebar.caption("ℹ️ 表格无 SPEC 列，已按所选数据自动估算上下限")

col_spec1, col_spec2, col_spec3 = st.sidebar.columns(3)
lsl = col_spec1.number_input(
    "LSL", key="spec_lsl_input", format="%.4f", on_change=on_spec_manual_change
)
target = col_spec2.number_input(
    "Target",
    key="spec_target_input",
    format="%.4f",
    on_change=on_spec_manual_change,
)
usl = col_spec3.number_input(
    "USL", key="spec_usl_input", format="%.4f", on_change=on_spec_manual_change
)

btn_label = (
    "🔄 重新获取表格 SPEC 上下限"
    if has_table_spec
    else "🔄 按当前所选列重新估算上下限"
)
if st.sidebar.button(btn_label, use_container_width=True):
  st.session_state["spec_manually_edited"] = False
  st.session_state["spec_lsl_input"] = rec_lsl
  st.session_state["spec_target_input"] = rec_target
  st.session_state["spec_usl_input"] = rec_usl
  st.rerun()

if lsl >= usl:
  st.sidebar.error("⚠️ LSL 必须小于 USL！请修改或点击上方按钮重置。")
  st.stop()

# ==================== 3. 全局统一数据屏蔽引擎（单点传感器/编码器尖峰 + 行级过滤） ====================
st.sidebar.header("3️⃣ 全局样本屏蔽")

# --- 3A. 单点传感器/编码器错误读数屏蔽 ---
spike_mode = st.sidebar.selectbox(
    "单点极端尖峰屏蔽（传感器/编码器 Bug）",
    options=[
        "智能抗差识别（偏离中位数 N 倍 MAD）",
        "按 SPEC 公差倍数识别（超出 Target ± N×公差）",
        "自定义单点有效数值区间",
        "不启用单点屏蔽",
    ],
    index=0,
    help="专门过滤某行个别通道混入的编码器/传感器错误值（如 11205.01），避免拉歪整体均值与箱线图。",
)

df_work = df_raw.copy()
sub_vals_raw = df_work[selected_value_cols].to_numpy(dtype=float)
spike_outlier_mask = np.zeros_like(sub_vals_raw, dtype=bool)

if spike_mode != "不启用单点屏蔽":
  sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
  if spike_mode == "智能抗差识别（偏离中位数 N 倍 MAD）":
    mad_mult = sp_c1.number_input(
        "MAD 阈值倍数",
        min_value=3.0,
        max_value=200.0,
        value=15.0,
        step=1.0,
        help="越小越严格；15 倍可精准抓出编码器跳变而不误伤正常波动。",
    )
    valid_flat = sub_vals_raw[~np.isnan(sub_vals_raw)]
    if len(valid_flat) > 0:
      med_all = float(np.median(valid_flat))
      mad_all = float(np.median(np.abs(valid_flat - med_all)))
      robust_sigma = mad_all * 1.4826
      if robust_sigma <= 1e-12:
        q75, q25 = np.percentile(valid_flat, [75, 25])
        robust_sigma = max((q75 - q25) / 1.349, (usl - lsl) / 6.0, 1e-6)
      low_bound = med_all - mad_mult * robust_sigma
      high_bound = med_all + mad_mult * robust_sigma
      spike_outlier_mask = (~np.isnan(sub_vals_raw)) & (
          (sub_vals_raw < low_bound) | (sub_vals_raw > high_bound)
      )
  elif spike_mode == "按 SPEC 公差倍数识别（超出 Target ± N×公差）":
    spec_mult = sp_c1.number_input(
        "公差跨度倍数",
        min_value=1.0,
        max_value=50.0,
        value=3.0,
        step=0.5,
    )
    spec_span = usl - lsl
    low_bound = target - spec_mult * spec_span
    high_bound = target + spec_mult * spec_span
    spike_outlier_mask = (~np.isnan(sub_vals_raw)) & (
        (sub_vals_raw < low_bound) | (sub_vals_raw > high_bound)
    )
  else:
    pt_min = sp_c1.number_input(
        "单点最小值", value=float(lsl - (usl - lsl)), format="%.4f"
    )
    pt_max = sp_c2.number_input(
        "单点最大值", value=float(usl + (usl - lsl)), format="%.4f"
    )
    spike_outlier_mask = (~np.isnan(sub_vals_raw)) & (
        (sub_vals_raw < pt_min) | (sub_vals_raw > pt_max)
    )

  if spike_mode != "自定义单点有效数值区间":
    spike_action = sp_c2.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
    )
  else:
    spike_action = st.sidebar.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
    )
else:
  spike_action = "置空该单元格（保留行内其他列）"

masked_cell_count = int(np.sum(spike_outlier_mask))
rows_with_spike_mask = np.any(spike_outlier_mask, axis=1)

if masked_cell_count > 0:
  if spike_action == "置空该单元格（保留行内其他列）":
    cleaned_vals = sub_vals_raw.copy()
    cleaned_vals[spike_outlier_mask] = np.nan
    for idx_c, col in enumerate(selected_value_cols):
      df_work[col] = cleaned_vals[:, idx_c]
    st.sidebar.caption(
        f"🛡️ 已自动置空 **{masked_cell_count}** 个传感器/编码器异常单元格"
    )
  else:
    st.sidebar.caption(
        f"🛡️ 已标记 **{int(np.sum(rows_with_spike_mask))}** 行含异常单点的数据行待剔除"
    )

# --- 3B. 行号区间与行均值筛选 ---
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

row_mean = df_work[selected_value_cols].mean(axis=1)
df_work["_Row_Mean_"] = row_mean

mask_not_nan = df_work["_Row_Mean_"].notna()
mask_not_in_range = ~df_work["Row_Index"].isin(excluded_rows_set)
mask_no_spike_row = (
    pd.Series(~rows_with_spike_mask, index=df_work.index)
    if (masked_cell_count > 0 and spike_action == "剔除包含异常点的整行")
    else pd.Series(True, index=df_work.index)
)
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

valid_mask = (
    mask_not_nan & mask_not_in_range & mask_no_spike_row & mask_value_ok
)
df_clean = df_work[valid_mask].copy().reset_index(drop=True)
df_removed = df_raw[~valid_mask].copy().reset_index(drop=True)

raw_sub_matrix = df_clean[selected_value_cols].to_numpy(dtype=float)
raw_all_valid_vals = raw_sub_matrix[~np.isnan(raw_sub_matrix)]

if len(raw_all_valid_vals) < 2:
  st.error("过滤后有效数据点不足 2 个，无法计算标准差与过程能力，请放宽筛选条件。")
  st.stop()


def compute_within_std(mat, flat_vals):
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

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("原始数据行数", len(df_work))
m2.metric("有效分析行数", len(df_clean))
m3.metric("已整行屏蔽数", len(df_removed))
m4.metric("已屏蔽异常单点", masked_cell_count)
m5.metric("总有效样本 N", len(all_valid_vals))

top_bar1, top_bar2 = st.columns([3.5, 1.2])
with top_bar1:
  with st.expander("✏️ 自定义项目名称与各图表主标题（点击展开）", expanded=False):
    t_col0, t_col1, t_col2 = st.columns(3)
    base_topic_name = t_col0.text_input(
        "项目 / 检测参数名称（自动同步至各图）",
        value=selected_sheet,
        placeholder="例如: Coating width A",
    )
    custom_title_cap = t_col1.text_input(
        "能力报告标题（留空自动生成）",
        value="",
        placeholder=f"{base_topic_name} — Process Capability Report",
    )
    custom_title_box = t_col2.text_input(
        "箱线图标题（留空自动生成）",
        value="",
        placeholder=f"{base_topic_name} — Box Plot",
    )
    t_col3, t_col4 = st.columns(2)
    custom_title_ts = t_col3.text_input(
        "时间序列图标题（留空自动生成）",
        value="",
        placeholder=f"{base_topic_name} — Time Series Plot",
    )
    custom_title_mean = t_col4.text_input(
        "单行均值图标题（留空自动生成）",
        value="",
        placeholder=f"{base_topic_name}均值",
    )

with top_bar2:
  show_outer_border = st.checkbox(
      "🖼️ 图像浅灰外边框",
      value=True,
      help="为导出图片添加浅灰色矩形边框，方便粘贴至 PPT 多图排版对齐",
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


# ==================== 统一图像浅灰色外边框封装 ====================
def save_fig_with_border(fig, use_tight=False):
  """保存图像为 PNG 字节流；启用边框时自动绘制与内容完美贴合的浅灰色外框"""
  fig.patch.set_facecolor("white")
  buf = io.BytesIO()
  if use_tight:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bbox_in = fig.get_tightbbox(renderer)
    pad_in = 0.14
    fig_w_in, fig_h_in = fig.get_size_inches()
    if show_outer_border and bbox_in is not None:
      x0 = (bbox_in.x0 - pad_in) / fig_w_in
      y0 = (bbox_in.y0 - pad_in) / fig_h_in
      w_norm = (bbox_in.width + 2 * pad_in) / fig_w_in
      h_norm = (bbox_in.height + 2 * pad_in) / fig_h_in
      border_rect = Rectangle(
          (x0, y0),
          w_norm,
          h_norm,
          transform=fig.transFigure,
          fill=False,
          edgecolor="#A6A6A6",
          linewidth=1.2,
          zorder=100,
          clip_on=False,
      )
      fig.patches.append(border_rect)
    fig.savefig(
        buf, format="png", dpi=170, bbox_inches="tight", pad_inches=pad_in
    )
  else:
    if show_outer_border:
      fig.patch.set_edgecolor("#A6A6A6")
      fig.patch.set_linewidth(2.2)
    fig.savefig(
        buf,
        format="png",
        dpi=170,
        facecolor=fig.get_facecolor(),
        edgecolor=fig.get_edgecolor(),
    )
  buf.seek(0)
  plt.close(fig)
  return buf


# ==================== 独立图表比例选择器组件 ====================
ASPECT_OPTIONS = [
    "4 : 3（PPT 多图/四宫格）",
    "3 : 2（紧凑双图对比）",
    "16 : 9（宽屏展示）",
    "2.2 : 1（超宽横幅）",
    "自定义比例",
]


def render_aspect_selector(container_col, key_prefix, default_idx=0):
  preset = container_col.selectbox(
      "图像比例",
      options=ASPECT_OPTIONS,
      index=default_idx,
      key=f"{key_prefix}_aspect_preset",
  )
  if preset == "4 : 3（PPT 多图/四宫格）":
    fw, fh = 9.6, 7.2
  elif preset == "3 : 2（紧凑双图对比）":
    fw, fh = 10.5, 7.0
  elif preset == "16 : 9（宽屏展示）":
    fw, fh = 12.8, 7.2
  elif preset == "2.2 : 1（超宽横幅）":
    fw, fh = 13.6, 6.2
  else:
    sub_c1, sub_c2 = container_col.columns(2)
    rw = sub_c1.number_input(
        "宽比",
        min_value=1.0,
        max_value=30.0,
        value=4.0,
        step=0.5,
        key=f"{key_prefix}_rw",
    )
    rh = sub_c2.number_input(
        "高比",
        min_value=1.0,
        max_value=30.0,
        value=3.0,
        step=0.5,
        key=f"{key_prefix}_rh",
    )
    fh = 7.0
    fw = float(np.clip(fh * (rw / rh), 6.5, 16.0))

  px_w = int(min(1150, max(620, fw * 85)))
  return fw, fh, px_w


# ==================== 图表渲染函数（自适应画布比例） ====================
def render_capability_plot(w_in, h_in):
  fig = plt.figure(figsize=(w_in, h_in), dpi=170)

  scale_f = min(w_in / 9.6, h_in / 7.2)
  font_panel = max(7.2, 8.3 * scale_f)
  font_title = max(11.5, 13.5 * scale_f)

  gs = fig.add_gridspec(
      2,
      3,
      width_ratios=[1.05, 2.35, 0.95],
      height_ratios=[3.6, 1.15],
      wspace=0.06,
      hspace=0.22,
  )

  ax_left = fig.add_subplot(gs[0, 0])
  ax_mid = fig.add_subplot(gs[0, 1])
  ax_right = fig.add_subplot(gs[0, 2])
  ax_bot_left = fig.add_subplot(gs[1, 0])
  ax_bot_mid = fig.add_subplot(gs[1, 1])
  ax_bot_right = fig.add_subplot(gs[1, 2])

  for ax_tmp in (ax_left, ax_right, ax_bot_left, ax_bot_mid, ax_bot_right):
    ax_tmp.axis("off")

  bins_count = min(38, max(14, int(np.sqrt(total_n) * 0.55)))
  counts, _, _ = ax_mid.hist(
      all_valid_vals,
      bins=bins_count,
      density=True,
      color="#78A2CC",
      edgecolor="#3A5F85",
      linewidth=0.55,
      alpha=0.92,
  )

  span = usl - lsl
  x_min_c = min(lsl - 0.18 * span, float(np.min(all_valid_vals)) - 0.08 * span)
  x_max_c = max(usl + 0.18 * span, float(np.max(all_valid_vals)) + 0.08 * span)
  x_grid = np.linspace(x_min_c, x_max_c, 500)

  line_ov, line_wi = None, None
  if std_overall > 0:
    (line_ov,) = ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, sample_mean, std_overall),
        color="#B91C1C",
        lw=1.8,
        ls="-",
        label="Overall",
    )
  if std_within > 0:
    (line_wi,) = ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, sample_mean, std_within),
        color="#374151",
        lw=1.6,
        ls="--",
        label="Within",
    )

  ax_mid.axvline(lsl, color="#DC2626", ls="--", lw=1.15)
  ax_mid.axvline(usl, color="#DC2626", ls="--", lw=1.15)
  ax_mid.axvline(target, color="#16A34A", ls=":", lw=1.1)

  y_peak = max(
      float(np.max(counts)) if len(counts) else 1.0,
      float(np.max(stats.norm.pdf(x_grid, sample_mean, std_within)))
      if std_within > 0
      else 1.0,
  )
  ax_mid.set_ylim(0, y_peak * 1.14)
  ax_mid.set_yticks([])
  ax_mid.tick_params(axis="x", labelsize=max(7.5, 8.8 * scale_f))
  ax_mid.grid(True, axis="x", ls=":", alpha=0.45)
  for sp in ("top", "right", "left", "bottom"):
    ax_mid.spines[sp].set_color("#CBD5E1")
    ax_mid.spines[sp].set_linewidth(0.8)

  lbl_sz = max(7.5, 8.5 * scale_f)
  ax_mid.text(
      lsl,
      y_peak * 1.16,
      f"LSL\n{lsl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
      fontweight="bold",
  )
  ax_mid.text(
      usl,
      y_peak * 1.16,
      f"USL\n{usl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
      fontweight="bold",
  )
  ax_mid.text(
      target,
      y_peak * 1.16,
      f"Target\n{target:.2f}",
      color="#15803D",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
  )

  left_text = (
      f"Process Data\n"
      f"----------------------\n"
      f"LSL          {lsl:.4f}\n"
      f"Target       {target:.4f}\n"
      f"USL          {usl:.4f}\n"
      f"Mean         {sample_mean:.4f}\n"
      f"Sample N     {total_n}\n"
      f"Valid Rows   {len(df_clean)}\n"
      f"Subgroup     {k_cols}\n"
      f"StDev(Ov)    {std_overall:.5f}\n"
      f"StDev(Wi)    {std_within:.5f}"
  )
  ax_left.text(
      0.95,
      0.96,
      left_text,
      transform=ax_left.transAxes,
      va="top",
      ha="right",
      fontsize=font_panel,
      fontfamily="monospace",
      color="#1E293B",
  )

  right_text = (
      f"Overall Capability\n"
      f"------------------\n"
      f"Pp        {pp:.2f}\n"
      f"PPL       {ppl:.2f}\n"
      f"PPU       {ppu:.2f}\n"
      f"Ppk       {ppk:.2f}\n\n"
      f"Potential (Within)\n"
      f"------------------\n"
      f"Cp        {cp:.2f}\n"
      f"CPL       {cpl:.2f}\n"
      f"CPU       {cpu:.2f}\n"
      f"Cpk       {cpk:.2f}"
  )
  ax_right.text(
      0.06,
      0.96,
      right_text,
      transform=ax_right.transAxes,
      va="top",
      ha="left",
      fontsize=font_panel,
      fontfamily="monospace",
      color="#1E293B",
  )

  handles_leg = [h for h in (line_ov, line_wi) if h is not None]
  if handles_leg:
    ax_bot_right.legend(
        handles=handles_leg,
        loc="upper left",
        bbox_to_anchor=(0.04, 0.98),
        fontsize=font_panel,
        frameon=True,
        facecolor="#F8FAFC",
        edgecolor="#CBD5E1",
    )

  ppm_text = (
      f"Performance (PPM)        Observed    Exp. Overall    Exp. Within\n"
      f"----------------------------------------------------------------\n"
      f"PPM < LSL               {obs_lt_lsl:9.2f}       {exp_ov_lt_lsl:9.2f}      {exp_wi_lt_lsl:9.2f}\n"
      f"PPM > USL               {obs_gt_usl:9.2f}       {exp_ov_gt_usl:9.2f}      {exp_wi_gt_usl:9.2f}\n"
      f"Total PPM               {obs_total:9.2f}       {exp_ov_total:9.2f}      {exp_wi_total:9.2f}"
  )
  ax_bot_mid.text(
      0.5,
      0.92,
      ppm_text,
      transform=ax_bot_mid.transAxes,
      va="top",
      ha="center",
      fontsize=max(7.0, font_panel * 0.96),
      fontfamily="monospace",
      color="#1E293B",
      bbox=dict(
          boxstyle="round,pad=0.4", facecolor="#F8FAFC", edgecolor="#E2E8F0"
      ),
  )

  fig.suptitle(
      final_title_cap,
      fontsize=font_title,
      fontweight="bold",
      y=0.96,
      fontproperties=FONT_PROP,
  )
  plt.subplots_adjust(left=0.025, right=0.975, top=0.835, bottom=0.045)

  return save_fig_with_border(fig, use_tight=False)


def render_box_plot(
    w_in,
    h_in,
    show_outliers=False,
    show_median_val=True,
    show_mean_val=False,
    decimals=4,
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=170)

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

  width_scale = min(w_in / 11.0, 1.15)
  label_font_size = (
      (8.2 if n_boxes <= 12 else (7.0 if n_boxes <= 22 else 6.0)) * width_scale
  )
  x_offset = box_width * 0.54
  fmt_str = f"{{:.{decimals}f}}"

  if show_mean_val:
    means_arr = [
        float(np.mean(arr)) if len(arr) > 0 else np.nan for arr in box_data
    ]
    ax.scatter(
        np.arange(1, n_boxes + 1),
        means_arr,
        color="#1D4ED8",
        edgecolor="white",
        s=22,
        zorder=5,
        label="Mean",
    )

  y_min_cur, y_max_cur = ax.get_ylim()
  y_span_cur = max(y_max_cur - y_min_cur, 1e-6)

  for idx, arr in enumerate(box_data):
    if len(arr) == 0:
      continue
    x_pos = (idx + 1) + x_offset
    med_v = float(np.median(arr))
    mean_v = float(np.mean(arr))

    if show_median_val and show_mean_val:
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

  if show_median_val or show_mean_val:
    ax.set_xlim(0.4, n_boxes + 1.05)

  ax_r = ax.twinx()
  ax_r.set_ylim(ax.get_ylim())
  ax_r.set_yticks([lsl, target, usl])
  ax_r.set_yticklabels(
      [f"{lsl}", f"{target}", f"{usl}"],
      color="#B91C1C",
      fontsize=8.8,
      fontweight="bold",
  )

  for sp in ("top", "right", "left", "bottom"):
    ax.spines[sp].set_color("#BFBFBF")
    ax.spines[sp].set_linewidth(0.8)
    ax_r.spines[sp].set_visible(False)

  ax.set_title(
      final_title_box,
      fontsize=max(11.5, 13.5 * width_scale),
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_ylabel("Value", fontsize=10)
  ax.tick_params(
      axis="x", rotation=45 if len(box_labels) > 5 else 0, labelsize=8.8
  )
  for lbl in ax.get_xticklabels():
    lbl.set_fontproperties(FONT_PROP)
  ax.grid(True, ls=":", alpha=0.45)
  plt.tight_layout(pad=1.2)

  return save_fig_with_border(fig, use_tight=False)


def render_time_series_plot(
    w_in, h_in, x_mode_opt, y_mode_opt, ymin_val=None, ymax_val=None
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=170)

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
        markersize=3.2,
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

  width_scale = min(w_in / 11.0, 1.15)
  ax.set_title(
      final_title_ts,
      fontsize=max(11.5, 13.5 * width_scale),
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_xlabel(x_label_text, fontsize=10)
  ax.set_ylabel("Value", fontsize=10)
  ax.grid(True, ls=":", alpha=0.45)

  handles, labels_ts = ax.get_legend_handles_labels()
  if w_in / h_in < 1.55:
    n_cols_leg = min(5, max(3, len(handles[:20]) // 3))
    leg = ax.legend(
        handles[:20],
        labels_ts[:20],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=n_cols_leg,
        prop=FONT_PROP,
        fontsize=7.6,
        frameon=True,
    )
  else:
    leg = ax.legend(
        handles[:20],
        labels_ts[:20],
        title="Variables" if len(handles) <= 20 else "Variables (Top 20)",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        prop=FONT_PROP,
        fontsize=8.0,
    )
    leg.get_title().set_fontsize(8.8)

  plt.tight_layout(pad=1.0)
  return save_fig_with_border(fig, use_tight=True)


def render_excel_style_row_mean_plot(
    w_in, h_in, x_mode_opt, y_mode_opt, ymin_val=None, ymax_val=None
):
  """复刻经典 Excel 折线图风格的单行均值趋势图"""
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=170)
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
      lw=2.5,
      label="目标值",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, usl, dtype=float),
      color="#ED7D31",
      lw=2.5,
      label="规格上限",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, lsl, dtype=float),
      color="#A5A5A5",
      lw=2.5,
      label="规格下限",
  )
  ax.plot(
      x_seq,
      y_mean_series,
      color="#FFC000",
      lw=2.2,
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
    n_ticks = max(12, int(w_in * 2.1))
    tick_step = max(1, len(x_seq) // n_ticks)
    tick_positions = x_seq[::tick_step]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(
        [str(v) for v in tick_positions],
        rotation=90,
        fontsize=9.0,
        color="#595959",
    )

  ax.tick_params(axis="y", labelsize=9.5, colors="#595959", length=0)
  ax.tick_params(axis="x", length=0, pad=5)

  ax.yaxis.grid(True, linestyle="-", linewidth=0.8, color="#D9D9D9")
  ax.xaxis.grid(False)
  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)
  ax.spines["left"].set_visible(False)
  ax.spines["bottom"].set_color("#D9D9D9")
  ax.spines["bottom"].set_linewidth(0.9)

  width_scale = min(w_in / 10.5, 1.15)
  ax.set_title(
      final_title_mean,
      fontsize=max(13.5, 16.5 * width_scale),
      fontweight="normal",
      color="#595959",
      pad=16,
      fontproperties=FONT_PROP,
  )

  leg = ax.legend(
      loc="upper center",
      bbox_to_anchor=(0.5, -0.14),
      ncol=4,
      frameon=False,
      prop=FONT_PROP,
      fontsize=10.5,
      handlelength=2.2,
      columnspacing=1.8,
  )
  for text in leg.get_texts():
    text.set_color("#595959")

  plt.tight_layout(pad=1.0)
  return save_fig_with_border(fig, use_tight=True)


# ==================== 独立分标签页（每张图独立控制比例与交互选项） ====================
tab_cap, tab_box, tab_ts, tab_mean, tab_data = st.tabs([
    "1️⃣ 过程能力报告 (CPK)",
    "2️⃣ 分组箱线图 (Box Plot)",
    "3️⃣ 多通道时间序列图 (Time Series)",
    "4️⃣ 单行均值趋势图 (Excel 风格)",
    "5️⃣ 清洗后数据明细与导出",
])

safe_prefix = re.sub(r'[\\/*?:"<>|]', "_", topic_clean)

with tab_cap:
  cc1, _ = st.columns([1.8, 3.2])
  cap_w, cap_h, cap_px = render_aspect_selector(cc1, "cap", default_idx=0)
  buf_cap = render_capability_plot(cap_w, cap_h)
  st.image(buf_cap, width=cap_px)
  buf_cap.seek(0)
  st.download_button(
      "🖼️ 下载当前过程能力报告图 (.png)",
      data=buf_cap,
      file_name=f"{safe_prefix}_CPK.png",
      mime="image/png",
  )

with tab_box:
  bc1, bc2, bc3, bc4, bc5 = st.columns([1.2, 1.2, 1.3, 0.9, 1.6])
  show_box_median = bc1.checkbox("显示中位数 (Median)", value=True)
  show_box_mean = bc2.checkbox("显示均值 (Mean)", value=False)
  show_box_outliers = bc3.checkbox("显示异常点 (Outliers)", value=False)
  box_decimals = bc4.selectbox(
      "小数位", options=[2, 3, 4, 5, 6], index=2
  )
  box_w, box_h, box_px = render_aspect_selector(bc5, "box", default_idx=0)

  buf_box = render_box_plot(
      box_w,
      box_h,
      show_outliers=show_box_outliers,
      show_median_val=show_box_median,
      show_mean_val=show_box_mean,
      decimals=box_decimals,
  )
  st.image(buf_box, width=box_px)
  buf_box.seek(0)
  st.download_button(
      "🖼️ 下载当前箱线图 (.png)",
      data=buf_box,
      file_name=f"{safe_prefix}_BoxPlot.png",
      mime="image/png",
  )

with tab_ts:
  tc1, tc2, tc3, tc4, tc5 = st.columns([1.6, 1.4, 0.9, 0.9, 1.5])
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
  ts_w, ts_h, ts_px = render_aspect_selector(tc5, "ts", default_idx=3)

  buf_ts = render_time_series_plot(
      ts_w, ts_h, ts_x_mode, ts_y_mode, ts_ymin, ts_ymax
  )
  st.image(buf_ts, width=ts_px)
  buf_ts.seek(0)
  st.download_button(
      "🖼️ 下载当前多通道时间序列图 (.png)",
      data=buf_ts,
      file_name=f"{safe_prefix}_TimeSeries.png",
      mime="image/png",
  )

with tab_mean:
  mc1, mc2, mc3, mc4, mc5 = st.columns([1.6, 1.4, 0.9, 0.9, 1.5])
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
  mean_w, mean_h, mean_px = render_aspect_selector(mc5, "mean", default_idx=3)

  buf_mean = render_excel_style_row_mean_plot(
      mean_w, mean_h, mean_x_mode, mean_y_mode, mean_ymin, mean_ymax
  )
  st.image(buf_mean, width=mean_px)
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