import base64
import io
import os
import re
import urllib.request
import zipfile
import matplotlib.font_manager as fm
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="在线检测 SPC 与过程能力分析系统",
    page_icon="📈",
    layout="wide",
)


def render_app_header():
  st.title("在线检测 SPC 与过程能力分析系统")
  st.caption("Created by xu")


COPY_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"'
    ' viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2'
    ' 2v1"></path></svg>'
)

CHECK_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"'
    ' viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="20 6 9 17 4 12"></polyline></svg>'
)


def render_copy_image_button(png_bytes, btn_key):
  """渲染与参考图标一致的复制按钮，点击将 PNG 图片写入系统剪贴板"""
  b64_png = base64.b64encode(png_bytes).decode("ascii")
  safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", btn_key)
  html_code = f"""
    <div style="display:flex;align-items:center;gap:6px;height:38px;">
      <button id="btn_{safe_id}" type="button" title="复制图片"
        style="display:inline-flex;align-items:center;justify-content:center;
               width:36px;height:36px;border-radius:8px;
               border:1px solid rgba(128,128,128,0.35);
               background:transparent;color:inherit;cursor:pointer;
               transition:background 0.15s ease;">
        {COPY_ICON_SVG}
      </button>
      <span id="msg_{safe_id}" style="font-size:12px;opacity:0.85;"></span>
    </div>
    <script>
      (function() {{
        const btn = document.getElementById("btn_{safe_id}");
        const msg = document.getElementById("msg_{safe_id}");
        const copySvg = `{COPY_ICON_SVG}`;
        const checkSvg = `{CHECK_ICON_SVG}`;
        const b64Data = "{b64_png}";
        if (!btn) return;
        btn.addEventListener("mouseenter", () => {{
          btn.style.background = "rgba(128,128,128,0.14)";
        }});
        btn.addEventListener("mouseleave", () => {{
          btn.style.background = "transparent";
        }});
        btn.addEventListener("click", async () => {{
          try {{
            const binStr = atob(b64Data);
            const len = binStr.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {{
              bytes[i] = binStr.charCodeAt(i);
            }}
            const blob = new Blob([bytes], {{ type: "image/png" }});
            if (navigator.clipboard && window.ClipboardItem) {{
              await navigator.clipboard.write([new ClipboardItem({{ "image/png": blob }})]);
              btn.innerHTML = checkSvg;
              msg.textContent = "已复制";
              setTimeout(() => {{
                btn.innerHTML = copySvg;
                msg.textContent = "";
              }}, 1800);
            }} else {{
              msg.textContent = "当前环境不支持复制，请点下载";
            }}
          }} catch (err) {{
            msg.textContent = "复制受限，请点下载";
          }}
        }});
      }})();
    </script>
    """
  components.html(html_code, height=42)


def render_chart_action_bar(png_buf, file_name, key_prefix):
  """在图表下方同一行展示精简的「下载」按钮与「复制」图标按钮"""
  png_bytes = png_buf.getvalue()
  a1, a2, _ = st.columns([0.95, 2.2, 6.85])
  with a1:
    st.download_button(
        "下载",
        data=png_bytes,
        file_name=file_name,
        mime="image/png",
        key=f"dl_{key_prefix}",
        use_container_width=True,
    )
  with a2:
    render_copy_image_button(png_bytes, f"cp_{key_prefix}")


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

# ==================== 1. 数据源与多项目分组识别 ====================
st.sidebar.header("1️⃣ 数据源与多项目分组")
uploaded_file = st.sidebar.file_uploader(
    "上传检测数据表 (.xlsx / .csv)", type=["xlsx", "xls", "csv"]
)

if uploaded_file is None:
  render_app_header()
  st.info(
      "👈 请在左侧边栏上传在线检测数据表格（第一行为表头，往下堆叠时间/检测数据）。"
  )
  st.stop()


def read_csv_compatible(file_bytes):
  """自动兼容 UTF-8 / GB18030 / GBK / Big5 及不同分隔符的 CSV 文件"""
  encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk", "big5"]
  last_err = None
  for enc in encodings:
    try:
      df = pd.read_csv(
          io.BytesIO(file_bytes),
          encoding=enc,
          sep=None,
          engine="python",
      )
      if df is not None and not df.empty:
        return df
    except UnicodeDecodeError as e:
      last_err = e
      continue
    except Exception:
      try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
        if df is not None and not df.empty:
          return df
      except Exception as e2:
        last_err = e2
        continue

  try:
    text_fallback = file_bytes.decode("gb18030", errors="replace")
    return pd.read_csv(io.StringIO(text_fallback), sep=None, engine="python")
  except Exception:
    raise last_err if last_err else ValueError("无法解析 CSV 文件")


@st.cache_data
def load_workbook_sheets(file_bytes, filename):
  lower_name = filename.lower()
  if lower_name.endswith(".csv"):
    df = read_csv_compatible(file_bytes)
    sheet_label = os.path.splitext(filename)[0] or "CSV_Data"
    return {sheet_label: df}

  engine = "openpyxl" if lower_name.endswith(".xlsx") else None
  xls = pd.ExcelFile(io.BytesIO(file_bytes), engine=engine)
  result = {}
  for name in xls.sheet_names:
    try:
      part_df = xls.parse(name)
      if part_df is not None and not part_df.dropna(how="all").empty:
        result[name] = part_df
    except Exception:
      continue
  if not result:
    result[xls.sheet_names[0]] = pd.DataFrame()
  return result


try:
  sheets_dict = load_workbook_sheets(
      uploaded_file.getvalue(), uploaded_file.name
  )
except Exception as exc:
  st.error(f"❌ 文件读取失败，请检查文件格式或编码：{exc}")
  st.stop()

selected_sheet = st.sidebar.selectbox(
    "工作表 (Sheet)", list(sheets_dict.keys())
)
df_raw = sheets_dict[selected_sheet].copy()
df_raw = df_raw.dropna(how="all").reset_index(drop=True)

if df_raw.empty:
  st.error("所选工作表无有效数据，请检查表格内容。")
  st.stop()

df_raw.insert(0, "Row_Index", np.arange(1, len(df_raw) + 1))

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
      "spec_cols": spec_cols_found,
  }


spec_info = detect_spec_from_columns(df_raw, df_raw.columns)
measurement_candidates = [
    c for c in numeric_cols_all if c not in spec_info["spec_cols"]
]
if not measurement_candidates:
  measurement_candidates = numeric_cols_all


def is_likely_non_measurement(name_str):
  """识别常见非质量检测数值列（日期、时间、编号、EA号、速度、走带距离、OK/NG统计等）"""
  s = str(name_str).strip().lower()
  non_meas_tokens = [
      "日期",
      "时间",
      "date",
      "time",
      "timestamp",
      "ea号",
      "编号",
      "序号",
      "工单",
      "卷号",
      "批次",
      "id",
      "no",
      "code",
      "速度",
      "speed",
      "走带",
      "长度",
      "米数",
      "meter",
      "len",
      "ok(",
      "ng(",
  ]
  return any(tok in s for tok in non_meas_tokens)


def infer_parameter_groups(cols):
  """按列名末尾数字/分隔符自动聚合成参数组（如 涂宽1..5 -> 涂宽）"""
  groups = {}
  order = []
  for c in cols:
    s = str(c).strip()
    prefix = re.sub(r"[\s_\-#]*\d+$", "", s).strip()
    if not prefix:
      prefix = s
    if prefix not in groups:
      groups[prefix] = []
      order.append(prefix)
    groups[prefix].append(c)
  return order, groups


group_order, inferred_groups = infer_parameter_groups(measurement_candidates)
suggested_default_groups = [
    g for g in group_order if not is_likely_non_measurement(g)
]

dataset_key = f"{uploaded_file.name}::{selected_sheet}"
if st.session_state.get("active_dataset_key") != dataset_key:
  st.session_state["active_dataset_key"] = dataset_key
  st.session_state["project_groups_map"] = {
      k: list(v) for k, v in inferred_groups.items()
  }
  st.session_state["draft_projects"] = list(suggested_default_groups)
  st.session_state["confirmed_projects"] = list(suggested_default_groups)
  st.session_state["confirmed_groups_snapshot"] = {
      k: list(v) for k, v in inferred_groups.items()
  }
  st.session_state["selection_dirty"] = False
  st.session_state["project_specs_map"] = {}
  st.session_state["draft_specs_map"] = {}
  st.session_state["spec_dirty"] = False

proj_map = st.session_state.setdefault(
    "project_groups_map", {k: list(v) for k, v in inferred_groups.items()}
)
available_proj_names = list(proj_map.keys())

draft_default = [
    p
    for p in st.session_state.get("draft_projects", suggested_default_groups)
    if p in available_proj_names
]

selected_projects = st.sidebar.multiselect(
    "待生成项目 / 参数组（已自动排除日期/编号等列）",
    options=available_proj_names,
    default=draft_default,
    key=f"ms_draft_projects_{dataset_key}",
    help="先选好需要出图的项目与通道列，再点击下方「生成 / 更新所选项目图表」，避免误选列拖慢操作。",
)
st.session_state["draft_projects"] = selected_projects

cols_changed_in_expander = False
with st.sidebar.expander("🔧 调整各项目包含的通道列", expanded=False):
  for p_name in available_proj_names:
    updated_cols = st.multiselect(
        f"[{p_name}] 通道列",
        options=numeric_cols_all,
        default=[c for c in proj_map[p_name] if c in numeric_cols_all],
        key=f"cols_for_{dataset_key}_{p_name}",
    )
    if updated_cols and updated_cols != proj_map[p_name]:
      proj_map[p_name] = updated_cols
      cols_changed_in_expander = True

  new_grp_name = st.text_input(
      "新增自定义项目组名称",
      value="",
      placeholder="例如: 涂宽+白边对比",
      key=f"new_grp_name_{dataset_key}",
  )
  new_grp_cols = st.multiselect(
      "选择新增项目组通道列",
      options=numeric_cols_all,
      default=[],
      key=f"new_grp_cols_{dataset_key}",
  )
  if st.button(
      "➕ 添加项目组",
      key=f"btn_add_grp_{dataset_key}",
      use_container_width=True,
  ):
    if new_grp_name.strip() and new_grp_cols:
      g_clean = new_grp_name.strip()
      proj_map[g_clean] = list(new_grp_cols)
      if g_clean not in st.session_state["draft_projects"]:
        st.session_state["draft_projects"].append(g_clean)
      st.session_state["selection_dirty"] = True
      st.rerun()

prev_confirmed = st.session_state.get("confirmed_projects", [])
prev_snapshot = st.session_state.get("confirmed_groups_snapshot", {})
current_selected_non_empty = [
    p for p in selected_projects if len(proj_map.get(p, [])) > 0
]
current_snapshot = {
    p: list(proj_map.get(p, [])) for p in current_selected_non_empty
}

if (
    current_selected_non_empty != prev_confirmed
    or current_snapshot != prev_snapshot
    or cols_changed_in_expander
):
  st.session_state["selection_dirty"] = True


def compute_recommended_spec(df_src, cols_sel, s_info):
  """使用中位数与抗差标准差(MAD)估算 SPEC，避免编码器尖峰带偏上下限"""
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


specs_map = st.session_state.setdefault("project_specs_map", {})
draft_specs_map = st.session_state.setdefault("draft_specs_map", {})

for p_name in current_selected_non_empty:
  p_key = f"{dataset_key}::{p_name}"
  if p_key not in specs_map:
    rl, rt, ru = compute_recommended_spec(df_raw, proj_map[p_name], spec_info)
    specs_map[p_key] = {"lsl": rl, "target": rt, "usl": ru}
  if p_key not in draft_specs_map:
    draft_specs_map[p_key] = dict(specs_map[p_key])


def _sync_draft_spec(p_key, field_name, widget_key):
  draft_specs_map.setdefault(p_key, dict(specs_map.get(p_key, {})))
  draft_specs_map[p_key][field_name] = float(st.session_state[widget_key])
  st.session_state["spec_dirty"] = True


generate_clicked = st.sidebar.button(
    "🚀 生成 / 更新所选项目图表",
    key=f"btn_gen_charts_{dataset_key}",
    type="primary",
    use_container_width=True,
)
if generate_clicked:
  st.session_state["confirmed_projects"] = list(current_selected_non_empty)
  st.session_state["confirmed_groups_snapshot"] = {
      p: list(proj_map.get(p, [])) for p in current_selected_non_empty
  }
  st.session_state["selection_dirty"] = False
  for p_name in current_selected_non_empty:
    p_key = f"{dataset_key}::{p_name}"
    if p_key in draft_specs_map:
      cand = draft_specs_map[p_key]
      if cand.get("lsl", 0.0) < cand.get("usl", 0.0):
        specs_map[p_key] = {
            "lsl": float(cand["lsl"]),
            "target": float(cand["target"]),
            "usl": float(cand["usl"]),
        }
  st.session_state["spec_dirty"] = False

if st.session_state.get("selection_dirty", False):
  render_app_header()
  if not current_selected_non_empty:
    st.info(
        "👈 当前未选择任何项目。请在左侧**「待生成项目 / 参数组」**中选择项目（或展开**「调整各项目包含的通道列」**），然后点击 **「🚀 生成 / 更新所选项目图表」**。"
    )
  else:
    st.warning(
        f"👈 检测到项目或通道列选择已变更（当前已选 {len(current_selected_non_empty)} 个项目：{', '.join(current_selected_non_empty)}）。已暂停自动出图，请点击左侧 **「🚀 生成 / 更新所选项目图表」** 开始生成。"
    )
  st.stop()

confirmed_projects = [
    p
    for p in st.session_state.get("confirmed_projects", [])
    if p in available_proj_names and len(proj_map.get(p, [])) > 0
]

if not confirmed_projects:
  render_app_header()
  st.info(
      "👈 请在左侧**「待生成项目 / 参数组」**中选择至少一个项目，然后点击 **「🚀 生成 / 更新所选项目图表」**。"
  )
  st.stop()

# ==================== 2. 各项目 SPEC 规格设定（草稿暂存，点按钮统一更新） ====================
st.sidebar.header("2️⃣ 各项目 SPEC 规格")
st.sidebar.caption("修改上下限或目标值时不会实时刷新图表，点上方按钮统一生效")

current_focus_proj = st.sidebar.selectbox(
    "当前编辑 SPEC 的项目",
    options=confirmed_projects,
    index=0,
    key=f"focus_spec_proj_{dataset_key}",
)
focus_key = f"{dataset_key}::{current_focus_proj}"
cur_draft_spec = draft_specs_map.setdefault(
    focus_key, dict(specs_map[focus_key])
)

sc1, sc2, sc3 = st.sidebar.columns(3)
lsl_w_key = f"num_lsl_{focus_key}"
tgt_w_key = f"num_target_{focus_key}"
usl_w_key = f"num_usl_{focus_key}"

sc1.number_input(
    "LSL",
    value=float(cur_draft_spec["lsl"]),
    format="%.4f",
    key=lsl_w_key,
    on_change=_sync_draft_spec,
    args=(focus_key, "lsl", lsl_w_key),
)
sc2.number_input(
    "Target",
    value=float(cur_draft_spec["target"]),
    format="%.4f",
    key=tgt_w_key,
    on_change=_sync_draft_spec,
    args=(focus_key, "target", tgt_w_key),
)
sc3.number_input(
    "USL",
    value=float(cur_draft_spec["usl"]),
    format="%.4f",
    key=usl_w_key,
    on_change=_sync_draft_spec,
    args=(focus_key, "usl", usl_w_key),
)

active_draft_lsl = float(draft_specs_map[focus_key]["lsl"])
active_draft_usl = float(draft_specs_map[focus_key]["usl"])
if active_draft_lsl >= active_draft_usl:
  st.sidebar.warning(f"⚠️ [{current_focus_proj}] LSL 应小于 USL，生效前请修正。")

if st.session_state.get("spec_dirty", False):
  st.sidebar.info("SPEC 已修改待生效：请点击上方「🚀 生成 / 更新所选项目图表」")

if st.sidebar.button(
    f"🔄 重新自动估算 [{current_focus_proj}] SPEC",
    key=f"btn_reest_spec_{focus_key}",
    use_container_width=True,
):
  rl, rt, ru = compute_recommended_spec(
      df_raw, proj_map[current_focus_proj], spec_info
  )
  draft_specs_map[focus_key] = {"lsl": rl, "target": rt, "usl": ru}
  st.session_state[lsl_w_key] = rl
  st.session_state[tgt_w_key] = rt
  st.session_state[usl_w_key] = ru
  st.session_state["spec_dirty"] = True
  st.rerun()

if len(confirmed_projects) > 1:
  with st.sidebar.expander("📋 批量查看/修改全部已生成项目 SPEC", expanded=False):
    for p_name in confirmed_projects:
      pk = f"{dataset_key}::{p_name}"
      d_sp = draft_specs_map.setdefault(pk, dict(specs_map[pk]))
      st.caption(f"**{p_name}**")
      b1, b2, b3 = st.columns(3)
      bl_k = f"batch_lsl_{pk}"
      bt_k = f"batch_tgt_{pk}"
      bu_k = f"batch_usl_{pk}"
      b1.number_input(
          "LSL",
          value=float(d_sp["lsl"]),
          format="%.4f",
          key=bl_k,
          on_change=_sync_draft_spec,
          args=(pk, "lsl", bl_k),
      )
      b2.number_input(
          "Target",
          value=float(d_sp["target"]),
          format="%.4f",
          key=bt_k,
          on_change=_sync_draft_spec,
          args=(pk, "target", bt_k),
      )
      b3.number_input(
          "USL",
          value=float(d_sp["usl"]),
          format="%.4f",
          key=bu_k,
          on_change=_sync_draft_spec,
          args=(pk, "usl", bu_k),
      )

# ==================== 3. 全局统一数据屏蔽引擎 ====================
st.sidebar.header("3️⃣ 全局样本屏蔽")

active_ref_lsl = float(specs_map[focus_key]["lsl"])
active_ref_usl = float(specs_map[focus_key]["usl"])

spike_mode = st.sidebar.selectbox(
    "单点极端尖峰屏蔽（传感器/编码器 Bug）",
    options=[
        "智能抗差识别（偏离中位数 N 倍 MAD）",
        "按各项目 SPEC 公差倍数识别",
        "自定义单点有效数值区间",
        "不启用单点屏蔽",
    ],
    index=0,
    key=f"spike_mode_{dataset_key}",
    help="专门过滤某行个别通道混入的编码器/传感器错误值，避免拉歪整体均值与箱线图。",
)

spike_param_val = 15.0
pt_min_val, pt_max_val = None, None
if spike_mode == "智能抗差识别（偏离中位数 N 倍 MAD）":
  sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
  spike_param_val = sp_c1.number_input(
      "MAD 阈值倍数",
      min_value=3.0,
      max_value=200.0,
      value=15.0,
      step=1.0,
      key=f"mad_mult_{dataset_key}",
  )
  spike_action = sp_c2.selectbox(
      "异常点处理方式",
      options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
      index=0,
      key=f"sp_act_mad_{dataset_key}",
  )
elif spike_mode == "按各项目 SPEC 公差倍数识别":
  sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
  spike_param_val = sp_c1.number_input(
      "公差跨度倍数",
      min_value=1.0,
      max_value=50.0,
      value=3.0,
      step=0.5,
      key=f"tol_mult_{dataset_key}",
  )
  spike_action = sp_c2.selectbox(
      "异常点处理方式",
      options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
      index=0,
      key=f"sp_act_tol_{dataset_key}",
  )
elif spike_mode == "自定义单点有效数值区间":
  sp_c1, sp_c2 = st.sidebar.columns(2)
  pt_min_val = sp_c1.number_input(
      "单点最小值",
      value=float(active_ref_lsl - (active_ref_usl - active_ref_lsl)),
      format="%.4f",
      key=f"pt_min_{dataset_key}",
  )
  pt_max_val = sp_c2.number_input(
      "单点最大值",
      value=float(active_ref_usl + (active_ref_usl - active_ref_lsl)),
      format="%.4f",
      key=f"pt_max_{dataset_key}",
  )
  spike_action = sp_c2.selectbox(
      "异常点处理方式",
      options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
      index=0,
      key=f"sp_act_rng_{dataset_key}",
  )
else:
  spike_action = "置空该单元格（保留行内其他列）"

exclude_ranges_str = st.sidebar.text_input(
    "屏蔽行号区间（支持多段）",
    value="",
    placeholder="例如: 1-250, 600-630",
    key=f"excl_rows_{dataset_key}",
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
        "按各项目 SPEC 范围过滤",
        "按自定义范围过滤（超出设定区间屏蔽）",
    ],
    index=1,
    key=f"filter_mode_{dataset_key}",
)

custom_min, custom_max = None, None
if filter_mode == "按自定义范围过滤（超出设定区间屏蔽）":
  c_min, c_max = st.sidebar.columns(2)
  custom_min = c_min.number_input(
      "允许最小值",
      value=float(active_ref_lsl),
      format="%.4f",
      key=f"c_min_{dataset_key}",
  )
  custom_max = c_max.number_input(
      "允许最大值",
      value=float(active_ref_usl),
      format="%.4f",
      key=f"c_max_{dataset_key}",
  )
  if custom_min >= custom_max:
    st.sidebar.error("⚠️ 最小值必须小于最大值！")
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


# ==================== 左侧最底部：西格玛 / CPK 波动美化校准 ====================
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 西格玛 / CPK 波动校准", expanded=False):
  sigma_target_proj = st.selectbox(
      "校准作用项目",
      options=["当前聚焦项目"] + confirmed_projects,
      index=0,
      key=f"sig_proj_{dataset_key}",
  )
  enable_sigma_tuning = st.checkbox(
      "启用西格玛美化校准（全图与导出表同步）",
      value=False,
      key=f"en_sig_{dataset_key}",
  )
  tuning_mode = st.radio(
      "校准方式",
      options=["直接指定目标西格玛 (σ)", "按目标 CPK 自动推算西格玛"],
      index=0,
      key=f"tun_mode_{dataset_key}",
  )
  center_align_pct = st.slider(
      "均值向 Target 居中比例 (%)",
      min_value=0,
      max_value=100,
      value=0,
      step=5,
      key=f"ctr_pct_{dataset_key}",
  )
  if tuning_mode == "直接指定目标西格玛 (σ)":
    manual_target_sigma = st.number_input(
        "目标组内西格玛 (Target Within σ)",
        min_value=0.000001,
        value=0.020000,
        format="%.6f",
        key=f"man_sig_{dataset_key}",
    )
    target_cpk_goal = 1.33
  else:
    manual_target_sigma = None
    target_cpk_goal = st.selectbox(
        "目标 CPK 标准",
        options=[1.33, 1.50, 1.67, 2.00],
        index=0,
        key=f"tgt_cpk_{dataset_key}",
    )


def build_project_dataset(p_name, proj_cols, p_lsl, p_target, p_usl):
  """为单个项目组生成清洗后数据、被剔除行、异常单点统计与西格玛校准结果"""
  df_w = df_raw.copy()
  sub_raw = df_w[proj_cols].to_numpy(dtype=float)
  sp_mask = np.zeros_like(sub_raw, dtype=bool)

  if spike_mode != "不启用单点屏蔽":
    if spike_mode == "智能抗差识别（偏离中位数 N 倍 MAD）":
      v_flat = sub_raw[~np.isnan(sub_raw)]
      if len(v_flat) > 0:
        med_v = float(np.median(v_flat))
        mad_v = float(np.median(np.abs(v_flat - med_v)))
        r_sig = mad_v * 1.4826
        if r_sig <= 1e-12:
          q75, q25 = np.percentile(v_flat, [75, 25])
          r_sig = max((q75 - q25) / 1.349, (p_usl - p_lsl) / 6.0, 1e-6)
        low_b = med_v - spike_param_val * r_sig
        high_b = med_v + spike_param_val * r_sig
        sp_mask = (~np.isnan(sub_raw)) & (
            (sub_raw < low_b) | (sub_raw > high_b)
        )
    elif spike_mode == "按各项目 SPEC 公差倍数识别":
      sp_span = p_usl - p_lsl
      low_b = p_target - spike_param_val * sp_span
      high_b = p_target + spike_param_val * sp_span
      sp_mask = (~np.isnan(sub_raw)) & ((sub_raw < low_b) | (sub_raw > high_b))
    elif (
        spike_mode == "自定义单点有效数值区间"
        and pt_min_val is not None
        and pt_max_val is not None
    ):
      sp_mask = (~np.isnan(sub_raw)) & (
          (sub_raw < pt_min_val) | (sub_raw > pt_max_val)
      )

  cell_cnt = int(np.sum(sp_mask))
  row_has_sp = np.any(sp_mask, axis=1)

  if cell_cnt > 0 and spike_action == "置空该单元格（保留行内其他列）":
    cleaned = sub_raw.copy()
    cleaned[sp_mask] = np.nan
    for idx_c, c_name in enumerate(proj_cols):
      df_w[c_name] = cleaned[:, idx_c]

  df_w["_Row_Mean_"] = df_w[proj_cols].mean(axis=1)

  m_not_nan = df_w["_Row_Mean_"].notna()
  m_not_rng = ~df_w["Row_Index"].isin(excluded_rows_set)
  m_no_sp_row = (
      pd.Series(~row_has_sp, index=df_w.index)
      if (cell_cnt > 0 and spike_action == "剔除包含异常点的整行")
      else pd.Series(True, index=df_w.index)
  )
  m_val_ok = pd.Series(True, index=df_w.index)

  if filter_mode == "按各项目 SPEC 范围过滤":
    m_val_ok = (df_w["_Row_Mean_"] >= p_lsl) & (df_w["_Row_Mean_"] <= p_usl)
  elif (
      filter_mode == "按自定义范围过滤（超出设定区间屏蔽）"
      and custom_min is not None
      and custom_max is not None
  ):
    m_val_ok = (df_w["_Row_Mean_"] >= custom_min) & (
        df_w["_Row_Mean_"] <= custom_max
    )

  v_mask = m_not_nan & m_not_rng & m_no_sp_row & m_val_ok
  df_c = df_w[v_mask].copy().reset_index(drop=True)
  df_r = df_raw[~v_mask].copy().reset_index(drop=True)

  s_mat_raw = df_c[proj_cols].to_numpy(dtype=float)
  v_vals_raw = s_mat_raw[~np.isnan(s_mat_raw)]
  if len(v_vals_raw) < 2:
    return None

  orig_m = float(np.mean(v_vals_raw))
  orig_wi = compute_within_std(s_mat_raw, v_vals_raw)

  apply_tuning = enable_sigma_tuning and (
      sigma_target_proj == "当前聚焦项目" and p_name == current_focus_proj
      or sigma_target_proj == p_name
  )

  if apply_tuning and orig_wi > 0:
    adj_mean = orig_m + (p_target - orig_m) * (center_align_pct / 100.0)
    if tuning_mode == "直接指定目标西格玛 (σ)" and manual_target_sigma is not None:
      tgt_wi = float(manual_target_sigma)
    else:
      min_dist = min(p_usl - adj_mean, adj_mean - p_lsl)
      tgt_wi = (
          min_dist / (3.0 * target_cpk_goal) if min_dist > 0 else orig_wi
      )
    ratio = tgt_wi / orig_wi
    for c_name in proj_cols:
      df_c[c_name] = adj_mean + (df_c[c_name] - orig_m) * ratio
    df_c["_Row_Mean_"] = df_c[proj_cols].mean(axis=1)

  s_mat = df_c[proj_cols].to_numpy(dtype=float)
  v_vals = s_mat[~np.isnan(s_mat)]
  s_mean = float(np.mean(v_vals))
  s_ov = float(np.std(v_vals, ddof=1))
  s_wi = compute_within_std(s_mat, v_vals)
  tot_n = len(v_vals)

  cp_v = (p_usl - p_lsl) / (6.0 * s_wi) if s_wi > 0 else np.nan
  cpl_v = (s_mean - p_lsl) / (3.0 * s_wi) if s_wi > 0 else np.nan
  cpu_v = (p_usl - s_mean) / (3.0 * s_wi) if s_wi > 0 else np.nan
  cpk_v = min(cpl_v, cpu_v)

  pp_v = (p_usl - p_lsl) / (6.0 * s_ov) if s_ov > 0 else np.nan
  ppl_v = (s_mean - p_lsl) / (3.0 * s_ov) if s_ov > 0 else np.nan
  ppu_v = (p_usl - s_mean) / (3.0 * s_ov) if s_ov > 0 else np.nan
  ppk_v = min(ppl_v, ppu_v)

  obs_lt = float(np.sum(v_vals < p_lsl)) / tot_n * 1e6
  obs_gt = float(np.sum(v_vals > p_usl)) / tot_n * 1e6
  obs_tot = obs_lt + obs_gt

  exp_ov_lt = (
      stats.norm.cdf((p_lsl - s_mean) / s_ov) * 1e6 if s_ov > 0 else 0.0
  )
  exp_ov_gt = (
      (1.0 - stats.norm.cdf((p_usl - s_mean) / s_ov)) * 1e6 if s_ov > 0 else 0.0
  )
  exp_ov_tot = exp_ov_lt + exp_ov_gt

  exp_wi_lt = (
      stats.norm.cdf((p_lsl - s_mean) / s_wi) * 1e6 if s_wi > 0 else 0.0
  )
  exp_wi_gt = (
      (1.0 - stats.norm.cdf((p_usl - s_mean) / s_wi)) * 1e6 if s_wi > 0 else 0.0
  )
  exp_wi_tot = exp_wi_lt + exp_wi_gt

  return {
      "cols": proj_cols,
      "lsl": p_lsl,
      "target": p_target,
      "usl": p_usl,
      "df_clean": df_c,
      "df_removed": df_r,
      "masked_cells": cell_cnt,
      "all_valid_vals": v_vals,
      "total_n": tot_n,
      "sample_mean": s_mean,
      "std_overall": s_ov,
      "std_within": s_wi,
      "cp": cp_v,
      "cpl": cpl_v,
      "cpu": cpu_v,
      "cpk": cpk_v,
      "pp": pp_v,
      "ppl": ppl_v,
      "ppu": ppu_v,
      "ppk": ppk_v,
      "obs_lt_lsl": obs_lt,
      "obs_gt_usl": obs_gt,
      "obs_total": obs_tot,
      "exp_ov_lt_lsl": exp_ov_lt,
      "exp_ov_gt_usl": exp_ov_gt,
      "exp_ov_total": exp_ov_tot,
      "exp_wi_lt_lsl": exp_wi_lt,
      "exp_wi_gt_usl": exp_wi_gt,
      "exp_wi_total": exp_wi_tot,
  }


project_bundles = {}
for p_name in confirmed_projects:
  pk = f"{dataset_key}::{p_name}"
  sp = specs_map[pk]
  if sp["lsl"] >= sp["usl"]:
    continue
  b_data = build_project_dataset(
      p_name, proj_map[p_name], sp["lsl"], sp["target"], sp["usl"]
  )
  if b_data is not None:
    project_bundles[p_name] = b_data

if not project_bundles:
  st.error(
      "当前筛选条件下，所选项目有效数据点不足 2 个或 SPEC 范围无效，请调整后点击「生成 / 更新所选项目图表」。"
  )
  st.stop()

ready_projects = list(project_bundles.keys())

# ==================== 顶部栏：标题、浅灰外边框开关与多项目一键 ZIP 打包 ====================
render_app_header()


def default_titles_for_project(p_name):
  return (
      f"{p_name} — Process Capability Report",
      f"{p_name} — Box Plot",
      f"{p_name} — Time Series Plot",
      f"{p_name}均值",
  )


def ensure_project_title_keys(p_name):
  d_cap, d_box, d_ts, d_mean = default_titles_for_project(p_name)
  k_cap = f"t_cap_{dataset_key}_{p_name}"
  k_box = f"t_box_{dataset_key}_{p_name}"
  k_ts = f"t_ts_{dataset_key}_{p_name}"
  k_mean = f"t_mean_{dataset_key}_{p_name}"
  st.session_state.setdefault(k_cap, d_cap)
  st.session_state.setdefault(k_box, d_box)
  st.session_state.setdefault(k_ts, d_ts)
  st.session_state.setdefault(k_mean, d_mean)
  return k_cap, k_box, k_ts, k_mean


top_bar1, top_bar2 = st.columns([3.5, 1.2])
with top_bar1:
  with st.expander(
      "✏️ 自定义各项目图表主标题（默认保留标准后缀，特殊情况可直接删改）",
      expanded=False,
  ):
    title_target_proj = st.selectbox(
        "选择要自定义标题的项目",
        options=ready_projects,
        key=f"title_proj_sel_{dataset_key}",
    )
    k_cap, k_box, k_ts, k_mean = ensure_project_title_keys(title_target_proj)
    t_c1, t_c2 = st.columns(2)
    t_c1.text_input("能力报告标题", key=k_cap)
    t_c2.text_input("箱线图标题", key=k_box)
    t_c3, t_c4 = st.columns(2)
    t_c3.text_input("时间序列图标题", key=k_ts)
    t_c4.text_input("单行均值图标题", key=k_mean)

    if st.button(
        f"↩️ 恢复 [{title_target_proj}] 默认标准后缀标题",
        key=f"reset_titles_{dataset_key}_{title_target_proj}",
    ):
      d_cap, d_box, d_ts, d_mean = default_titles_for_project(title_target_proj)
      st.session_state[k_cap] = d_cap
      st.session_state[k_box] = d_box
      st.session_state[k_ts] = d_ts
      st.session_state[k_mean] = d_mean
      st.rerun()

with top_bar2:
  show_outer_border = st.checkbox(
      "🖼️ 图像浅灰外边框",
      value=True,
      key=f"show_border_{dataset_key}",
      help="为导出图片添加浅灰色矩形边框，方便粘贴至 PPT 多图排版对齐",
  )


def get_project_titles(p_name):
  """严格按输入框当前值生成标题；若用户主动留空，则回退该项目的默认标准后缀"""
  d_cap, d_box, d_ts, d_mean = default_titles_for_project(p_name)
  k_cap, k_box, k_ts, k_mean = ensure_project_title_keys(p_name)
  v_cap = str(st.session_state.get(k_cap, "")).strip()
  v_box = str(st.session_state.get(k_box, "")).strip()
  v_ts = str(st.session_state.get(k_ts, "")).strip()
  v_mean = str(st.session_state.get(k_mean, "")).strip()
  return (
      v_cap if v_cap else d_cap,
      v_box if v_box else d_box,
      v_ts if v_ts else d_ts,
      v_mean if v_mean else d_mean,
  )


# ==================== 统一图像浅灰色外边框封装 ====================
def save_fig_with_border(fig, use_tight=False):
  fig.patch.set_facecolor("white")
  buf = io.BytesIO()
  try:
    if use_tight:
      fig.canvas.draw()
      renderer = getattr(fig.canvas, "get_renderer", lambda: None)()
      fig_w_in, fig_h_in = fig.get_size_inches()
      pad_in = 0.14
      if show_outer_border and renderer is not None:
        bbox_in = fig.get_tightbbox(renderer)
        if (
            bbox_in is not None
            and bbox_in.width > 0
            and bbox_in.height > 0
            and fig_w_in > 0
            and fig_h_in > 0
        ):
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
  except Exception:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
  buf.seek(0)
  plt.close(fig)
  return buf


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
      key=f"{key_prefix}_{dataset_key}_aspect_preset",
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
        key=f"{key_prefix}_{dataset_key}_rw",
    )
    rh = sub_c2.number_input(
        "高比",
        min_value=1.0,
        max_value=30.0,
        value=3.0,
        step=0.5,
        key=f"{key_prefix}_{dataset_key}_rh",
    )
    fh = 7.0
    fw = float(np.clip(fh * (rw / rh), 6.5, 16.0))

  px_w = int(min(1150, max(620, fw * 85)))
  return fw, fh, px_w


# ==================== 单项目四张图渲染函数 ====================
def render_capability_plot(b, title_str, w_in, h_in):
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

  all_v = b["all_valid_vals"]
  tot_n = b["total_n"]
  s_mean = b["sample_mean"]
  s_ov = b["std_overall"]
  s_wi = b["std_within"]
  p_lsl, p_target, p_usl = b["lsl"], b["target"], b["usl"]

  bins_count = min(38, max(14, int(np.sqrt(tot_n) * 0.55)))
  counts, _, _ = ax_mid.hist(
      all_v,
      bins=bins_count,
      density=True,
      color="#78A2CC",
      edgecolor="#3A5F85",
      linewidth=0.55,
      alpha=0.92,
  )

  span = max(p_usl - p_lsl, 1e-6)
  x_min_c = min(p_lsl - 0.18 * span, float(np.min(all_v)) - 0.08 * span)
  x_max_c = max(p_usl + 0.18 * span, float(np.max(all_v)) + 0.08 * span)
  if abs(x_max_c - x_min_c) < 1e-9:
    x_min_c -= 1.0
    x_max_c += 1.0
  x_grid = np.linspace(x_min_c, x_max_c, 500)

  line_ov, line_wi = None, None
  if s_ov > 1e-12:
    (line_ov,) = ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, s_mean, s_ov),
        color="#B91C1C",
        lw=1.8,
        ls="-",
        label="Overall",
    )
  if s_wi > 1e-12:
    (line_wi,) = ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, s_mean, s_wi),
        color="#374151",
        lw=1.6,
        ls="--",
        label="Within",
    )

  ax_mid.axvline(p_lsl, color="#DC2626", ls="--", lw=1.15)
  ax_mid.axvline(p_usl, color="#DC2626", ls="--", lw=1.15)
  ax_mid.axvline(p_target, color="#16A34A", ls=":", lw=1.1)

  y_peak = max(
      float(np.max(counts)) if len(counts) else 1.0,
      float(np.max(stats.norm.pdf(x_grid, s_mean, s_wi)))
      if s_wi > 1e-12
      else 1.0,
      1e-6,
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
      p_lsl,
      y_peak * 1.16,
      f"LSL\n{p_lsl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
      fontweight="bold",
  )
  ax_mid.text(
      p_usl,
      y_peak * 1.16,
      f"USL\n{p_usl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
      fontweight="bold",
  )
  ax_mid.text(
      p_target,
      y_peak * 1.16,
      f"Target\n{p_target:.2f}",
      color="#15803D",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
  )

  left_text = (
      f"Process Data\n"
      f"----------------------\n"
      f"LSL          {p_lsl:.4f}\n"
      f"Target       {p_target:.4f}\n"
      f"USL          {p_usl:.4f}\n"
      f"Mean         {s_mean:.4f}\n"
      f"Sample N     {tot_n}\n"
      f"Valid Rows   {len(b['df_clean'])}\n"
      f"Subgroup     {len(b['cols'])}\n"
      f"StDev(Ov)    {s_ov:.5f}\n"
      f"StDev(Wi)    {s_wi:.5f}"
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
      f"Pp        {b['pp']:.2f}\n"
      f"PPL       {b['ppl']:.2f}\n"
      f"PPU       {b['ppu']:.2f}\n"
      f"Ppk       {b['ppk']:.2f}\n\n"
      f"Potential (Within)\n"
      f"------------------\n"
      f"Cp        {b['cp']:.2f}\n"
      f"CPL       {b['cpl']:.2f}\n"
      f"CPU       {b['cpu']:.2f}\n"
      f"Cpk       {b['cpk']:.2f}"
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
      f"PPM < LSL               {b['obs_lt_lsl']:9.2f}       {b['exp_ov_lt_lsl']:9.2f}      {b['exp_wi_lt_lsl']:9.2f}\n"
      f"PPM > USL               {b['obs_gt_usl']:9.2f}       {b['exp_ov_gt_usl']:9.2f}      {b['exp_wi_gt_usl']:9.2f}\n"
      f"Total PPM               {b['obs_total']:9.2f}       {b['exp_ov_total']:9.2f}      {b['exp_wi_total']:9.2f}"
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
      title_str,
      fontsize=font_title,
      fontweight="bold",
      y=0.96,
      fontproperties=FONT_PROP,
  )
  plt.subplots_adjust(left=0.025, right=0.975, top=0.835, bottom=0.045)
  return save_fig_with_border(fig, use_tight=False)


def render_box_plot(
    b,
    title_str,
    w_in,
    h_in,
    show_outliers=False,
    show_median_val=True,
    show_mean_val=False,
    decimals=4,
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=170)
  df_c = b["df_clean"]
  p_cols = b["cols"]
  p_lsl, p_target, p_usl = b["lsl"], b["target"], b["usl"]

  box_data = [
      arr if len(arr) > 0 else np.array([p_target], dtype=float)
      for arr in (df_c[c].dropna().to_numpy(dtype=float) for c in p_cols)
  ]
  box_labels = [str(c) for c in p_cols]
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

  ax.axhline(p_usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(p_target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(p_lsl, color="#DC2626", ls="--", lw=1.2)

  width_scale = min(w_in / 11.0, 1.15)
  label_font_size = (
      (8.2 if n_boxes <= 12 else (7.0 if n_boxes <= 22 else 6.0)) * width_scale
  )
  x_offset = box_width * 0.54
  fmt_str = f"{{:.{decimals}f}}"

  if show_mean_val:
    means_arr = [float(np.mean(arr)) for arr in box_data]
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
  ax_r.set_yticks([p_lsl, p_target, p_usl])
  ax_r.set_yticklabels(
      [f"{p_lsl}", f"{p_target}", f"{p_usl}"],
      color="#B91C1C",
      fontsize=8.8,
      fontweight="bold",
  )

  for sp in ("top", "right", "left", "bottom"):
    ax.spines[sp].set_color("#BFBFBF")
    ax.spines[sp].set_linewidth(0.8)
    ax_r.spines[sp].set_visible(False)

  ax.set_title(
      title_str,
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
    b, title_str, w_in, h_in, x_mode_opt, y_mode_opt, ymin_val=None, ymax_val=None
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=170)
  df_c = b["df_clean"]
  p_cols = b["cols"]
  p_lsl, p_target, p_usl = b["lsl"], b["target"], b["usl"]

  if x_mode_opt == "保留原始表格行号 (Row Index)":
    x_seq = df_c["Row_Index"].to_numpy(dtype=int)
    x_label_text = "Original Row Index"
  else:
    x_seq = np.arange(1, len(df_c) + 1)
    x_label_text = "Filtered Sequence Index (1..N)"

  markers = ["o", "s", "D", "^", "v", "<", ">", "p", "*", "h"]
  cmap = plt.get_cmap("tab20")
  step_mark = max(1, len(x_seq) // 250)

  for idx, col_name in enumerate(p_cols):
    y_col = df_c[col_name].to_numpy(dtype=float)
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

  ax.axhline(p_usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(p_target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(p_lsl, color="#DC2626", ls="--", lw=1.2)

  if (
      y_mode_opt == "自定义范围 (Manual)"
      and ymin_val is not None
      and ymax_val is not None
      and ymin_val < ymax_val
  ):
    ax.set_ylim(ymin_val, ymax_val)

  width_scale = min(w_in / 11.0, 1.15)
  ax.set_title(
      title_str,
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
    ax.legend(
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
    b, title_str, w_in, h_in, x_mode_opt, y_mode_opt, ymin_val=None, ymax_val=None
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=170)
  ax.set_facecolor("white")
  df_c = b["df_clean"]
  p_lsl, p_target, p_usl = b["lsl"], b["target"], b["usl"]

  if x_mode_opt == "保留原始表格行号 (Row Index)":
    x_seq = df_c["Row_Index"].to_numpy(dtype=int)
  else:
    x_seq = np.arange(1, len(df_c) + 1)

  y_mean_series = df_c["_Row_Mean_"].to_numpy(dtype=float)

  ax.plot(
      x_seq,
      np.full_like(x_seq, p_target, dtype=float),
      color="#4472C4",
      lw=2.5,
      label="目标值",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, p_usl, dtype=float),
      color="#ED7D31",
      lw=2.5,
      label="规格上限",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, p_lsl, dtype=float),
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
    spec_span = max(p_usl - p_lsl, 1e-6)
    y_low = min(
        p_lsl - 0.5 * spec_span,
        float(np.min(y_mean_series)) - 0.15 * spec_span,
    )
    y_high = max(
        p_usl + 0.25 * spec_span,
        float(np.max(y_mean_series)) + 0.15 * spec_span,
    )
    if abs(y_high - y_low) < 1e-9:
      y_low -= 1.0
      y_high += 1.0
    ax.set_ylim(y_low, y_high)

  if len(x_seq) >= 2 and x_seq[-1] > x_seq[0]:
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
      title_str,
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


# ==================== 多项目汇总表与一键打包 ZIP ====================
summary_rows = []
for p_name in ready_projects:
  b = project_bundles[p_name]
  summary_rows.append({
      "项目组": p_name,
      "通道数": len(b["cols"]),
      "有效行数": len(b["df_clean"]),
      "总样本 N": b["total_n"],
      "屏蔽异常单点": b["masked_cells"],
      "LSL": b["lsl"],
      "Target": b["target"],
      "USL": b["usl"],
      "均值": round(b["sample_mean"], 4),
      "组内σ": round(b["std_within"], 5),
      "CPK": round(b["cpk"], 2),
      "PPK": round(b["ppk"], 2),
  })
df_summary = pd.DataFrame(summary_rows)
st.dataframe(df_summary, width="stretch", hide_index=True)

if len(ready_projects) > 1:
  zip_buf = io.BytesIO()
  with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for p_name in ready_projects:
      b = project_bundles[p_name]
      t_cap, t_box, t_ts, t_mean = get_project_titles(p_name)
      safe_p = re.sub(r'[\\/*?:"<>|]', "_", p_name)
      zf.writestr(
          f"{safe_p}/{safe_p}_CPK.png",
          render_capability_plot(b, t_cap, 9.6, 7.2).getvalue(),
      )
      zf.writestr(
          f"{safe_p}/{safe_p}_BoxPlot.png",
          render_box_plot(b, t_box, 9.6, 7.2).getvalue(),
      )
      zf.writestr(
          f"{safe_p}/{safe_p}_TimeSeries.png",
          render_time_series_plot(
              b, t_ts, 13.6, 6.2, "连续重排序号 (1..N，无断层)", "自动缩放 (Auto)"
          ).getvalue(),
      )
      zf.writestr(
          f"{safe_p}/{safe_p}_RowMean_Trend.png",
          render_excel_style_row_mean_plot(
              b, t_mean, 13.6, 6.2, "连续重排序号 (1..N，无断层)", "自动缩放 (Auto)"
          ).getvalue(),
      )
  zip_buf.seek(0)
  safe_sheet = re.sub(r'[\\/*?:"<>|]', "_", selected_sheet)
  st.download_button(
      "下载",
      data=zip_buf,
      file_name=f"{safe_sheet}_多项目SPC图表包.zip",
      mime="application/zip",
      key=f"dl_zip_{dataset_key}",
  )

# ==================== 按项目分标签页展示全套图表与导出 ====================
proj_tabs = st.tabs([f"📊 {p_name}" for p_name in ready_projects])

for p_tab, p_name in zip(proj_tabs, ready_projects):
  with p_tab:
    b = project_bundles[p_name]
    t_cap, t_box, t_ts, t_mean = get_project_titles(p_name)
    safe_prefix = re.sub(r'[\\/*?:"<>|]', "_", p_name)
    all_v = b["all_valid_vals"]
    p_lsl, p_usl = b["lsl"], b["usl"]

    tab_cap, tab_box, tab_ts, tab_mean, tab_data = st.tabs([
        "1️⃣ 过程能力报告 (CPK)",
        "2️⃣ 分组箱线图 (Box Plot)",
        "3️⃣ 多通道时间序列图 (Time Series)",
        "4️⃣ 单行均值趋势图 (Excel 风格)",
        "5️⃣ 清洗后数据明细与导出",
    ])

    with tab_cap:
      cc1, _ = st.columns([1.8, 3.2])
      cap_w, cap_h, cap_px = render_aspect_selector(
          cc1, f"cap_{p_name}", default_idx=0
      )
      buf_cap = render_capability_plot(b, t_cap, cap_w, cap_h)
      st.image(buf_cap, width=cap_px)
      render_chart_action_bar(
          buf_cap, f"{safe_prefix}_CPK.png", f"cap_{dataset_key}_{p_name}"
      )

    with tab_box:
      bc1, bc2, bc3, bc4, bc5 = st.columns([1.2, 1.2, 1.3, 0.9, 1.6])
      show_box_median = bc1.checkbox(
          "显示中位数 (Median)",
          value=True,
          key=f"bmed_{dataset_key}_{p_name}",
      )
      show_box_mean = bc2.checkbox(
          "显示均值 (Mean)", value=False, key=f"bmean_{dataset_key}_{p_name}"
      )
      show_box_outliers = bc3.checkbox(
          "显示异常点 (Outliers)",
          value=False,
          key=f"bout_{dataset_key}_{p_name}",
      )
      box_decimals = bc4.selectbox(
          "小数位",
          options=[2, 3, 4, 5, 6],
          index=2,
          key=f"bdec_{dataset_key}_{p_name}",
      )
      box_w, box_h, box_px = render_aspect_selector(
          bc5, f"box_{p_name}", default_idx=0
      )

      buf_box = render_box_plot(
          b,
          t_box,
          box_w,
          box_h,
          show_outliers=show_box_outliers,
          show_median_val=show_box_median,
          show_mean_val=show_box_mean,
          decimals=box_decimals,
      )
      st.image(buf_box, width=box_px)
      render_chart_action_bar(
          buf_box, f"{safe_prefix}_BoxPlot.png", f"box_{dataset_key}_{p_name}"
      )

    with tab_ts:
      tc1, tc2, tc3, tc4, tc5 = st.columns([1.6, 1.4, 0.9, 0.9, 1.5])
      ts_x_mode = tc1.selectbox(
          "X轴序号",
          options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
          index=0,
          key=f"ts_x_{dataset_key}_{p_name}",
      )
      ts_y_mode = tc2.selectbox(
          "Y轴尺度",
          options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
          index=0,
          key=f"ts_y_{dataset_key}_{p_name}",
      )
      d_ymin, d_ymax = float(np.min(all_v)), float(np.max(all_v))
      pad = max((d_ymax - d_ymin) * 0.1, 0.02)
      ts_ymin, ts_ymax = None, None
      if ts_y_mode == "自定义范围 (Manual)":
        ts_ymin = tc3.number_input(
            "Y-Min",
            value=round(d_ymin - pad, 4),
            format="%.4f",
            key=f"ts_ymin_{dataset_key}_{p_name}",
        )
        ts_ymax = tc4.number_input(
            "Y-Max",
            value=round(d_ymax + pad, 4),
            format="%.4f",
            key=f"ts_ymax_{dataset_key}_{p_name}",
        )
      ts_w, ts_h, ts_px = render_aspect_selector(
          tc5, f"ts_{p_name}", default_idx=3
      )

      buf_ts = render_time_series_plot(
          b, t_ts, ts_w, ts_h, ts_x_mode, ts_y_mode, ts_ymin, ts_ymax
      )
      st.image(buf_ts, width=ts_px)
      render_chart_action_bar(
          buf_ts,
          f"{safe_prefix}_TimeSeries.png",
          f"ts_{dataset_key}_{p_name}",
      )

    with tab_mean:
      mc1, mc2, mc3, mc4, mc5 = st.columns([1.6, 1.4, 0.9, 0.9, 1.5])
      mean_x_mode = mc1.selectbox(
          "X轴序号",
          options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
          index=0,
          key=f"mean_x_{dataset_key}_{p_name}",
      )
      mean_y_mode = mc2.selectbox(
          "Y轴尺度",
          options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
          index=0,
          key=f"mean_y_{dataset_key}_{p_name}",
      )
      mean_ymin, mean_ymax = None, None
      if mean_y_mode == "自定义范围 (Manual)":
        spec_span = p_usl - p_lsl
        mean_ymin = mc3.number_input(
            "Y-Min",
            value=round(p_lsl - 0.5 * spec_span, 4),
            format="%.4f",
            key=f"mean_ymin_{dataset_key}_{p_name}",
        )
        mean_ymax = mc4.number_input(
            "Y-Max",
            value=round(p_usl + 0.25 * spec_span, 4),
            format="%.4f",
            key=f"mean_ymax_{dataset_key}_{p_name}",
        )
      mean_w, mean_h, mean_px = render_aspect_selector(
          mc5, f"mean_{p_name}", default_idx=3
      )

      buf_mean = render_excel_style_row_mean_plot(
          b, t_mean, mean_w, mean_h, mean_x_mode, mean_y_mode, mean_ymin, mean_ymax
      )
      st.image(buf_mean, width=mean_px)
      render_chart_action_bar(
          buf_mean,
          f"{safe_prefix}_RowMean_Trend.png",
          f"mean_{dataset_key}_{p_name}",
      )

    with tab_data:
      excel_buf = io.BytesIO()
      with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        b["df_clean"].to_excel(writer, sheet_name="Valid_Data", index=False)
        b["df_removed"].to_excel(
            writer, sheet_name="Filtered_Out_Rows", index=False
        )
      excel_buf.seek(0)
      st.download_button(
          "下载",
          data=excel_buf,
          file_name=f"{safe_prefix}_Filtered.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          key=f"dl_xlsx_{dataset_key}_{p_name}",
      )
      sub_t1, sub_t2 = st.tabs(
          ["有效数据 (Valid)", "被屏蔽异常行 (Filtered Out)"]
      )
      with sub_t1:
        st.dataframe(b["df_clean"], width="stretch")
      with sub_t2:
        st.dataframe(b["df_removed"], width="stretch")