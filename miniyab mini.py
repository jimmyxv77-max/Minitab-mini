import io
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

plt.rcParams["axes.unicode_minus"] = False

st.title("📈 在线检测 SPC 与过程能力分析系统（Minitab 风格）")
st.caption(
    "适配多样化在线检测表格（第1行为表头，往下堆叠数据）｜支持在线 SPEC 设定、行均值异常屏蔽、Box Plot 离群点开关与时间序列 Y 轴自定义"
)
st.markdown("---")

# ==================== 1. 文件上传与 Sheet 选择 ====================
st.sidebar.header("1️⃣ 数据上传与表头识别")
uploaded_file = st.sidebar.file_uploader(
    "上传在线检测数据表 (.xlsx / .csv)", type=["xlsx", "xls", "csv"]
)

if uploaded_file is None:
  st.info(
      "👈 请在左侧边栏上传在线检测数据表格（支持 Excel 多工作表或 CSV），即可开始配置 SPEC、异常行屏蔽并生成 Minitab 风格图表。"
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

# 清理完全空行/空列
df_raw = df_raw.dropna(how="all").reset_index(drop=True)

if df_raw.empty:
  st.error("所选工作表无有效数据，请检查表格内容。")
  st.stop()

# 识别数值列
numeric_cols_all = []
for col in df_raw.columns:
  converted = pd.to_numeric(df_raw[col], errors="coerce")
  non_null = df_raw[col].notna().sum()
  if non_null > 0 and converted.notna().sum() / non_null >= 0.3:
    df_raw[col] = converted
    numeric_cols_all.append(col)

# ==================== 2. 列选择与在线 SPEC 设定 ====================
st.sidebar.header("2️⃣ 检测列与分组设置")
selected_value_cols = st.sidebar.multiselect(
    "选择检测数据列（可多选，将按行求均值参与行过滤与分析）",
    options=numeric_cols_all,
    default=numeric_cols_all[: min(3, len(numeric_cols_all))],
)

if not selected_value_cols:
  st.warning("请至少选择一列检测数值列。")
  st.stop()

group_col_options = ["无分组（整体分析）"] + list(df_raw.columns)
selected_group_col = st.sidebar.selectbox(
    "选择箱线图分组列 / 时间列（可选）", options=group_col_options, index=0
)

st.sidebar.header("3️⃣ 在线 SPEC 规格设定")
col_spec1, col_spec2, col_spec3 = st.sidebar.columns(3)
lsl = col_spec1.number_input("LSL (下限)", value=122.4, format="%.4f")
target = col_spec2.number_input("Target (目标)", value=124.4, format="%.4f")
usl = col_spec3.number_input("USL (上限)", value=126.4, format="%.4f")

if lsl >= usl:
  st.sidebar.error("⚠️ LSL 必须小于 USL！")
  st.stop()

# ==================== 4. 行均值异常屏蔽逻辑 ====================
st.sidebar.header("4️⃣ 数据筛选与异常行屏蔽")
filter_mode = st.sidebar.radio(
    "选择行均值筛选规则",
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

valid_mask = df_work["_Row_Mean_"].notna()

if filter_mode == "按 SPEC 范围过滤（行均值超出 [LSL, USL] 屏蔽）":
  valid_mask = (
      valid_mask & (df_work["_Row_Mean_"] >= lsl) & (df_work["_Row_Mean_"] <= usl)
  )
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
  valid_mask = (
      valid_mask
      & (df_work["_Row_Mean_"] >= custom_min)
      & (df_work["_Row_Mean_"] <= custom_max)
  )

df_clean = df_work[valid_mask].copy().reset_index(drop=True)
df_removed = df_work[~valid_mask].copy().reset_index(drop=True)

# ==================== 5. 图表显示与坐标轴控制 ====================
st.sidebar.header("5️⃣ 图表细节与坐标轴设置")
show_box_outliers = st.sidebar.checkbox(
    "Box Plot 显示异常点（Outliers）", value=True
)

ts_y_mode = st.sidebar.radio(
    "时间序列图纵坐标（Y轴）尺度",
    options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
    index=0,
)

y = df_clean["_Row_Mean_"].to_numpy(dtype=float)
default_ymin = float(np.min(y)) if len(y) > 0 else float(lsl)
default_ymax = float(np.max(y)) if len(y) > 0 else float(usl)
pad = max((default_ymax - default_ymin) * 0.1, 0.05)

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

# 筛选摘要指标
m1, m2, m3 = st.columns(3)
m1.metric("原始数据行数", len(df_work))
m2.metric("屏蔽后有效行数", len(df_clean))
m3.metric("已屏蔽异常行数", len(df_removed))

if len(df_clean) < 2:
  st.error("过滤后有效数据少于 2 行，无法计算标准差与过程能力，请放宽筛选条件。")
  st.stop()

# ==================== 6. 统计计算与 Minitab 风格绘图 ====================
n = len(y)
mean_y = float(np.mean(y))
std_overall = float(np.std(y, ddof=1))

if n > 1:
  mr = np.abs(np.diff(y))
  mean_mr = float(np.mean(mr))
  std_within = mean_mr / 1.12838 if mean_mr > 0 else std_overall
else:
  std_within = std_overall

cp = (usl - lsl) / (6.0 * std_within) if std_within > 0 else np.nan
cpu = (usl - mean_y) / (3.0 * std_within) if std_within > 0 else np.nan
cpl = (mean_y - lsl) / (3.0 * std_within) if std_within > 0 else np.nan
cpk = min(cpu, cpl)

pp = (usl - lsl) / (6.0 * std_overall) if std_overall > 0 else np.nan
ppu = (usl - mean_y) / (3.0 * std_overall) if std_overall > 0 else np.nan
ppl = (mean_y - lsl) / (3.0 * std_overall) if std_overall > 0 else np.nan
ppk = min(ppu, ppl)

ppm_lt_lsl = (
    stats.norm.cdf((lsl - mean_y) / std_overall) * 1e6
    if std_overall > 0
    else 0.0
)
ppm_gt_usl = (
    (1.0 - stats.norm.cdf((usl - mean_y) / std_overall)) * 1e6
    if std_overall > 0
    else 0.0
)
ppm_total = ppm_lt_lsl + ppm_gt_usl

ucl = mean_y + 3.0 * std_within
lcl = mean_y - 3.0 * std_within

fig = plt.figure(figsize=(15, 9.5), dpi=140)
fig.patch.set_facecolor("white")

# 上方：过程能力分析
ax1 = fig.add_subplot(2, 2, (1, 2))
bins_count = min(20, max(8, int(np.sqrt(n) * 1.5)))
counts, bins, _ = ax1.hist(
    y,
    bins=bins_count,
    density=True,
    color="#7FA6C9",
    edgecolor="#3B5B78",
    alpha=0.85,
    label="Histogram",
)

x_min = min(lsl, float(np.min(y))) - 0.15 * (usl - lsl)
x_max = max(usl, float(np.max(y))) + 0.15 * (usl - lsl)
x_grid = np.linspace(x_min, x_max, 400)

if std_within > 0:
  ax1.plot(
      x_grid,
      stats.norm.pdf(x_grid, mean_y, std_within),
      color="#1B365D",
      lw=2.0,
      ls="-",
      label="Within",
  )
if std_overall > 0:
  ax1.plot(
      x_grid,
      stats.norm.pdf(x_grid, mean_y, std_overall),
      color="#C0392B",
      lw=1.8,
      ls="--",
      label="Overall",
  )

ax1.axvline(lsl, color="#C0392B", ls="--", lw=1.6)
ax1.axvline(target, color="#27AE60", ls="-", lw=1.6)
ax1.axvline(usl, color="#C0392B", ls="--", lw=1.6)

y_top = (
    max(
        float(np.max(counts)) if len(counts) else 1.0,
        float(np.max(stats.norm.pdf(x_grid, mean_y, std_within)))
        if std_within > 0
        else 1.0,
    )
    * 1.18
)
ax1.set_ylim(0, y_top)

label_y = y_top * 0.90
ax1.text(
    lsl,
    label_y,
    f"LSL={lsl:.3f}",
    color="#C0392B",
    ha="center",
    fontsize=8.5,
    fontweight="bold",
    bbox=dict(boxstyle="round,pad=0.2", facecolor="#FDEDEC", edgecolor="none"),
)
ax1.text(
    target,
    label_y,
    f"Target={target:.3f}",
    color="#1E8449",
    ha="center",
    fontsize=8.5,
    fontweight="bold",
    bbox=dict(boxstyle="round,pad=0.2", facecolor="#EAFAF1", edgecolor="none"),
)
ax1.text(
    usl,
    label_y,
    f"USL={usl:.3f}",
    color="#C0392B",
    ha="center",
    fontsize=8.5,
    fontweight="bold",
    bbox=dict(boxstyle="round,pad=0.2", facecolor="#FDEDEC", edgecolor="none"),
)

col_desc = ", ".join(str(c) for c in selected_value_cols[:3]) + (
    "..." if len(selected_value_cols) > 3 else ""
)
ax1.set_title(
    f"Process Capability Analysis — [{col_desc}]",
    fontsize=12.5,
    fontweight="bold",
    pad=10,
)
ax1.set_xlabel("Row Mean Value", fontsize=10)
ax1.set_ylabel("Density", fontsize=10)
ax1.legend(loc="upper left", fontsize=8.5, frameon=True)
ax1.grid(True, ls=":", alpha=0.4)

stats_box = (
    f"Process Spec & Stats\n"
    f"--------------------\n"
    f"USL   : {usl:.4f}\n"
    f"Target: {target:.4f}\n"
    f"LSL   : {lsl:.4f}\n"
    f"Mean  : {mean_y:.4f}\n"
    f"n     : {n}\n"
    f"--------------------\n"
    f"Potential (Within)\n"
    f"StDev : {std_within:.4f}\n"
    f"Cp    : {cp:.2f}\n"
    f"Cpk   : {cpk:.2f}\n"
    f"--------------------\n"
    f"Overall (Long-term)\n"
    f"StDev : {std_overall:.4f}\n"
    f"Pp    : {pp:.2f}\n"
    f"Ppk   : {ppk:.2f}\n"
    f"--------------------\n"
    f"Exp. PPM (Overall)\n"
    f"< LSL : {ppm_lt_lsl:.1f}\n"
    f"> USL : {ppm_gt_usl:.1f}\n"
    f"Total : {ppm_total:.1f}"
)
ax1.text(
    1.02,
    0.5,
    stats_box,
    transform=ax1.transAxes,
    va="center",
    ha="left",
    fontsize=8.2,
    fontfamily="monospace",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="#F8FAFC", edgecolor="#CBD5E1"),
)

# 左下：箱线图 Box Plot（支持异常点显示/隐藏）
ax2 = fig.add_subplot(2, 2, 3)
flier_props = dict(
    marker="o",
    markerfacecolor="#DC2626",
    markeredgecolor="#DC2626",
    markersize=4.5,
)

if selected_group_col != "无分组（整体分析）":
  grp_series = df_clean[selected_group_col].astype(str)
  unique_grps = grp_series.unique()[:12]
  grp_data = [
      df_clean.loc[grp_series == g, "_Row_Mean_"].dropna().to_numpy()
      for g in unique_grps
  ]
  grp_data_filtered = [
      (g, d) for g, d in zip(unique_grps, grp_data) if len(d) > 0
  ]
  if grp_data_filtered:
    labels_bp = [item[0] for item in grp_data_filtered]
    data_bp = [item[1] for item in grp_data_filtered]
    ax2.boxplot(
        data_bp,
        labels=labels_bp,
        patch_artist=True,
        showmeans=True,
        showfliers=show_box_outliers,
        meanprops=dict(
            marker="D",
            markerfacecolor="#E67E22",
            markeredgecolor="black",
            markersize=5.5,
        ),
        medianprops=dict(color="#111827", linewidth=1.8),
        boxprops=dict(facecolor="#93C5FD", edgecolor="#1E40AF", alpha=0.85),
        flierprops=flier_props,
    )
    ax2.set_title(
        f"Box Plot by {selected_group_col}", fontsize=11.5, fontweight="bold"
    )
    ax2.set_xlabel(str(selected_group_col), fontsize=9.5)
    ax2.tick_params(axis="x", rotation=25)
  else:
    ax2.boxplot(
        [y],
        labels=["All Data"],
        patch_artist=True,
        showmeans=True,
        showfliers=show_box_outliers,
        flierprops=flier_props,
    )
    ax2.set_title("Box Plot (All Data)", fontsize=11.5, fontweight="bold")
else:
  ax2.boxplot(
      [y],
      labels=["All Data"],
      patch_artist=True,
      showmeans=True,
      showfliers=show_box_outliers,
      meanprops=dict(
          marker="D",
          markerfacecolor="#E67E22",
          markeredgecolor="black",
          markersize=6,
      ),
      medianprops=dict(color="#111827", linewidth=2),
      boxprops=dict(facecolor="#93C5FD", edgecolor="#1E40AF", alpha=0.85),
      flierprops=flier_props,
  )
  ax2.set_title("Box Plot (All Valid Rows)", fontsize=11.5, fontweight="bold")

ax2.axhline(
    target, color="#27AE60", ls="--", lw=1.2, label=f"Target ({target:.3f})"
)
ax2.set_ylabel("Row Mean Value", fontsize=9.5)
ax2.legend(loc="best", fontsize=8)
ax2.grid(True, ls=":", alpha=0.4)

# 右下：时间序列 / 移动单值控制图 (I Chart)（支持 Y 轴自定义）
ax3 = fig.add_subplot(2, 2, 4)
x_idx = np.arange(1, n + 1)
ax3.plot(
    x_idx,
    y,
    color="#2563EB",
    lw=1.3,
    marker="o",
    markersize=4.2,
    label="Row Mean",
)

ooc = (y > ucl) | (y < lcl)
if np.any(ooc):
  ax3.scatter(
      x_idx[ooc], y[ooc], color="#DC2626", s=50, zorder=5, label="Out of 3σ"
  )

ax3.axhline(mean_y, color="#16A34A", ls="-", lw=1.5, label=f"Mean ({mean_y:.3f})")
ax3.axhline(ucl, color="#DC2626", ls="--", lw=1.2, label=f"UCL ({ucl:.3f})")
ax3.axhline(lcl, color="#DC2626", ls="--", lw=1.2, label=f"LCL ({lcl:.3f})")

if ts_y_mode == "自定义范围 (Manual)" and ts_ymin is not None and ts_ymax is not None:
  ax3.set_ylim(ts_ymin, ts_ymax)

ax3.set_title(
    "Time Series Plot (I Control Chart)", fontsize=11.5, fontweight="bold"
)
ax3.set_xlabel("Sequence (Filtered Rows)", fontsize=9.5)
ax3.set_ylabel("Row Mean Value", fontsize=9.5)
ax3.legend(loc="upper right", fontsize=8, ncol=2)
ax3.grid(True, ls=":", alpha=0.4)

plt.tight_layout(rect=[0, 0, 0.85, 1])

img_buf = io.BytesIO()
plt.savefig(img_buf, format="png", dpi=150)
img_buf.seek(0)
plt.close(fig)

st.subheader("📊 Minitab 风格综合分析图表")
st.image(img_buf, use_container_width=True)

dl_col1, dl_col2 = st.columns(2)
with dl_col1:
  img_buf.seek(0)
  st.download_button(
      label="🖼️ 下载高清分析图 (.png)",
      data=img_buf,
      file_name=f"Minitab_SPC_{selected_sheet}.png",
      mime="image/png",
  )

with dl_col2:
  excel_buf = io.BytesIO()
  with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
    df_clean.to_excel(writer, sheet_name="Valid_Data", index=False)
    df_removed.to_excel(writer, sheet_name="Filtered_Out_Rows", index=False)
  excel_buf.seek(0)
  st.download_button(
      label="📥 导出有效数据与被屏蔽异常行 (.xlsx)",
      data=excel_buf,
      file_name=f"Filtered_Data_{selected_sheet}.xlsx",
      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  )

with st.expander("🔍 查看屏蔽后有效数据与被剔除的异常行", expanded=False):
  t1, t2 = st.tabs(["有效数据 (Valid)", "被屏蔽异常行 (Filtered Out)"])
  with t1:
    st.dataframe(df_clean, use_container_width=True)
  with t2:
    st.dataframe(df_removed, use_container_width=True)