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

APP_VERSION = "v2.0"
APP_EDITION_TAG = "v2.0 · 多批次对比版"

st.set_page_config(
    page_title="在线检测 SPC 与过程能力分析系统 (v2.0 多批次对比)",
    page_icon="📊",
    layout="wide",
)


def render_app_header(compact=False):
  """2.0 启动页与主界面顶部统一标识，明显区分于 1.0"""
  st.markdown(
      """
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px;">
          <span style="background:#2563EB;color:#FFFFFF;font-size:12px;font-weight:700;
                       padding:3px 10px;border-radius:999px;letter-spacing:0.5px;">
            v2.0 · 多批次对比版
          </span>
          <span style="font-size:12px;color:#64748B;">
            共享项目与 SPEC 设定 · 多批次同屏对比汇报
          </span>
        </div>
        """,
      unsafe_allow_html=True,
  )
  st.title("在线检测 SPC 与过程能力分析系统")
  st.caption("Created by xu  |  版本 2.0（多批次联合分析与对比）")
  if not compact:
    st.markdown(
        """
            <div style="border-left:4px solid #2563EB;background:rgba(37,99,235,0.06);
                        padding:10px 14px;border-radius:0 8px 8px 0;margin:8px 0 14px 0;font-size:13px;">
              <strong>2.0 多批次工作流：</strong>
              1) 在左侧上传 <strong>2–3 个同表头批次文件</strong>；
              2) 统一配置<strong>待生成项目</strong>与 <strong>SPEC</strong>（修改规格不实时刷新，点按钮统一生效）；
              3) 保留<strong>单点极端尖峰屏蔽</strong>与<strong>西格玛/CPK 校准</strong>，快速对比各批次表现，挑出最适合汇报的批次。
            </div>
            """,
        unsafe_allow_html=True,
    )


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
  """渲染紧邻下载按钮的复制图标按钮，点击将 PNG 图片写入系统剪贴板"""
  b64_png = base64.b64encode(png_bytes).decode("ascii")
  safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", btn_key)
  html_code = f"""
    <div style="display:flex;align-items:center;gap:6px;height:38px;margin:0;padding:0;">
      <button id="btn_{safe_id}" type="button" title="复制图片"
        style="display:inline-flex;align-items:center;justify-content:center;
               width:38px;height:38px;border-radius:8px;
               border:1px solid rgba(150,150,160,0.38);
               background:transparent;color:inherit;cursor:pointer;
               transition:background 0.15s ease,border-color 0.15s ease;">
        {COPY_ICON_SVG}
      </button>
      <span id="msg_{safe_id}" style="font-size:12px;white-space:nowrap;opacity:0.85;"></span>
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
          btn.style.background = "rgba(128,128,128,0.15)";
          btn.style.borderColor = "rgba(150,150,160,0.6)";
        }});
        btn.addEventListener("mouseleave", () => {{
          btn.style.background = "transparent";
          btn.style.borderColor = "rgba(150,150,160,0.38)";
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
              msg.textContent = "不支持复制，请点下载";
            }}
          }} catch (err) {{
            msg.textContent = "复制受限，请点下载";
          }}
        }});
      }})();
    </script>
    """
  components.html(html_code, height=40)


def render_chart_action_bar(png_buf, file_name, key_prefix):
  """紧凑并排展示「下载」按钮与「复制」图标按钮"""
  png_bytes = png_buf.getvalue()
  a1, a2, _ = st.columns([0.85, 2.15, 7.0], gap="small")
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


def prepare_clean_raw_df(raw_sheet_df):
  df_w = raw_sheet_df.dropna(how="all").reset_index(drop=True).copy()
  if df_w.empty:
    return None, []
  df_w.insert(0, "Row_Index", np.arange(1, len(df_w) + 1))
  num_cols = []
  for col in df_w.columns:
    if col == "Row_Index":
      continue
    converted = pd.to_numeric(df_w[col], errors="coerce")
    non_null = df_w[col].notna().sum()
    if non_null > 0 and converted.notna().sum() / non_null >= 0.3:
      df_w[col] = converted
      num_cols.append(col)
  return df_w, num_cols


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


def is_likely_non_measurement(name_str):
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


# ==================== 1. 多批次数据源（建议 2-3 个同表头批次文件） ====================
st.sidebar.header("1️⃣ 多批次数据源（2-3个批次）")
uploaded_files = st.sidebar.file_uploader(
    "上传 2–3 个批次检测数据表 (.xlsx / .csv)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    help="建议同时选择 2–3 个表头一致的批次文件，系统将自动共用项目、SPEC 与屏蔽/校准设定进行对比。",
)

if not uploaded_files or len(uploaded_files) < 2:
  render_app_header(compact=False)
  if not uploaded_files:
    st.info(
        "👈 请在左侧边栏上传 **2–3 个批次**的检测数据表格（建议表头相同，便于共用项目与 SPEC 设定）。"
    )
  else:
    st.warning(
        f"当前仅上传了 1 个文件（{uploaded_files[0].name}）。2.0 多批次对比版建议同时上传 **2–3 个批次文件**进行对比；请继续添加批次文件。"
    )
  st.stop()

if len(uploaded_files) > 3:
  st.sidebar.caption(
      f"已上传 {len(uploaded_files)} 个批次文件，当前将全部纳入多批次对比。"
  )

batch_entries = []
for f_idx, up_file in enumerate(uploaded_files):
  try:
    s_dict = load_workbook_sheets(up_file.getvalue(), up_file.name)
  except Exception as exc:
    st.error(f"❌ 批次文件 [{up_file.name}] 读取失败：{exc}")
    st.stop()
  sheet_names = list(s_dict.keys())
  default_sh_idx = 0
  chosen_sheet = st.sidebar.selectbox(
      f"批次 {f_idx + 1} 工作表 ({up_file.name})",
      options=sheet_names,
      index=default_sh_idx,
      key=f"v2_sheet_{f_idx}_{up_file.name}",
  )
  df_clean_raw, num_cols = prepare_clean_raw_df(s_dict[chosen_sheet])
  if df_clean_raw is None or not num_cols:
    st.error(
        f"❌ 批次 [{up_file.name} - {chosen_sheet}] 未识别到有效数值检测列。"
    )
    st.stop()

  batch_label = f"批次{f_idx + 1}: {os.path.splitext(up_file.name)[0]}"
  # 若有重名批次标签，追加序号保证唯一
  if any(b["label"] == batch_label for b in batch_entries):
    batch_label = f"{batch_label} (#{f_idx + 1})"

  batch_entries.append({
      "idx": f_idx,
      "file_name": up_file.name,
      "sheet": chosen_sheet,
      "label": batch_label,
      "df_raw": df_clean_raw,
      "numeric_cols": num_cols,
      "spec_info": detect_spec_from_columns(df_clean_raw, df_clean_raw.columns),
  })

# 计算各批次公共数值列（若表头完全一致，则全部数值列都在交集中）
common_numeric_cols = [
    c
    for c in batch_entries[0]["numeric_cols"]
    if all(c in b["numeric_cols"] for b in batch_entries[1:])
]
union_numeric_cols = []
for b in batch_entries:
  for c in b["numeric_cols"]:
    if c not in union_numeric_cols:
      union_numeric_cols.append(c)

shared_pool_cols = (
    common_numeric_cols if common_numeric_cols else union_numeric_cols
)
if not common_numeric_cols:
  st.sidebar.warning(
      "⚠️ 各批次数值表头不完全一致，已自动取并集列，请核对各项目通道列。"
  )

# 首选从首个含 SPEC 列的批次提取默认 SPEC
merged_spec_info = {"lsl": None, "target": None, "usl": None, "spec_cols": set()}
for b in batch_entries:
  for k_sp in ("lsl", "target", "usl"):
    if merged_spec_info[k_sp] is None and b["spec_info"][k_sp] is not None:
      merged_spec_info[k_sp] = b["spec_info"][k_sp]
  merged_spec_info["spec_cols"].update(b["spec_info"]["spec_cols"])

measurement_candidates = [
    c for c in shared_pool_cols if c not in merged_spec_info["spec_cols"]
]
if not measurement_candidates:
  measurement_candidates = shared_pool_cols

group_order, inferred_groups = infer_parameter_groups(measurement_candidates)
suggested_default_groups = [
    g for g in group_order if not is_likely_non_measurement(g)
]

dataset_key = "||".join(
    f"{b['file_name']}::{b['sheet']}" for b in batch_entries
)

if st.session_state.get("v2_active_dataset_key") != dataset_key:
  st.session_state["v2_active_dataset_key"] = dataset_key
  st.session_state["v2_project_groups_map"] = {
      k: list(v) for k, v in inferred_groups.items()
  }
  st.session_state["v2_draft_projects"] = list(suggested_default_groups)
  st.session_state["v2_confirmed_projects"] = list(suggested_default_groups)
  st.session_state["v2_confirmed_groups_snapshot"] = {
      k: list(v) for k, v in inferred_groups.items()
  }
  st.session_state["v2_selection_dirty"] = False
  st.session_state["v2_project_specs_map"] = {}
  st.session_state["v2_draft_specs_map"] = {}
  st.session_state["v2_spec_dirty"] = False

proj_map = st.session_state.setdefault(
    "v2_project_groups_map", {k: list(v) for k, v in inferred_groups.items()}
)
available_proj_names = list(proj_map.keys())

draft_default = [
    p
    for p in st.session_state.get(
        "v2_draft_projects", suggested_default_groups
    )
    if p in available_proj_names
]

selected_projects = st.sidebar.multiselect(
    "共用待生成项目 / 参数组",
    options=available_proj_names,
    default=draft_default,
    key=f"v2_ms_draft_projects_{dataset_key}",
    help="多批次共用同一套项目分组与通道列，选好后点击「🚀 生成 / 更新所选项目图表」。",
)
st.session_state["v2_draft_projects"] = selected_projects

cols_changed_in_expander = False
with st.sidebar.expander("🔧 调整各项目共用的通道列", expanded=False):
  for p_name in available_proj_names:
    updated_cols = st.multiselect(
        f"[{p_name}] 通道列",
        options=shared_pool_cols,
        default=[c for c in proj_map[p_name] if c in shared_pool_cols],
        key=f"v2_cols_for_{dataset_key}_{p_name}",
    )
    if updated_cols and updated_cols != proj_map[p_name]:
      proj_map[p_name] = updated_cols
      cols_changed_in_expander = True

  new_grp_name = st.text_input(
      "新增共用项目组名称",
      value="",
      placeholder="例如: 涂宽+白边对比",
      key=f"v2_new_grp_name_{dataset_key}",
  )
  new_grp_cols = st.multiselect(
      "选择新增项目组通道列",
      options=shared_pool_cols,
      default=[],
      key=f"v2_new_grp_cols_{dataset_key}",
  )
  if st.button(
      "➕ 添加共用项目组",
      key=f"v2_btn_add_grp_{dataset_key}",
      use_container_width=True,
  ):
    if new_grp_name.strip() and new_grp_cols:
      g_clean = new_grp_name.strip()
      proj_map[g_clean] = list(new_grp_cols)
      if g_clean not in st.session_state["v2_draft_projects"]:
        st.session_state["v2_draft_projects"].append(g_clean)
      st.session_state["v2_selection_dirty"] = True
      st.rerun()

prev_confirmed = st.session_state.get("v2_confirmed_projects", [])
prev_snapshot = st.session_state.get("v2_confirmed_groups_snapshot", {})
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
  st.session_state["v2_selection_dirty"] = True


def compute_recommended_spec_multi(b_list, cols_sel, s_info):
  """基于多批次样本中位数与 MAD 估算共用 SPEC，避免编码器尖峰带偏上下限"""
  all_pieces = []
  for b in b_list:
    valid_cols = [c for c in cols_sel if c in b["df_raw"].columns]
    if valid_cols:
      arr = b["df_raw"][valid_cols].to_numpy(dtype=float)
      vv = arr[~np.isnan(arr)]
      if len(vv) > 0:
        all_pieces.append(vv)

  if all_pieces:
    valid_v = np.concatenate(all_pieces)
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


specs_map = st.session_state.setdefault("v2_project_specs_map", {})
draft_specs_map = st.session_state.setdefault("v2_draft_specs_map", {})

for p_name in current_selected_non_empty:
  p_key = f"{dataset_key}::{p_name}"
  if p_key not in specs_map:
    rl, rt, ru = compute_recommended_spec_multi(
        batch_entries, proj_map[p_name], merged_spec_info
    )
    specs_map[p_key] = {"lsl": rl, "target": rt, "usl": ru}
  if p_key not in draft_specs_map:
    draft_specs_map[p_key] = dict(specs_map[p_key])


def _sync_v2_draft_spec(p_key, field_name, widget_key):
  draft_specs_map.setdefault(p_key, dict(specs_map.get(p_key, {})))
  draft_specs_map[p_key][field_name] = float(st.session_state[widget_key])
  st.session_state["v2_spec_dirty"] = True


generate_clicked = st.sidebar.button(
    "🚀 生成 / 更新所选项目图表",
    key=f"v2_btn_gen_charts_{dataset_key}",
    type="primary",
    use_container_width=True,
)
if generate_clicked:
  st.session_state["v2_confirmed_projects"] = list(current_selected_non_empty)
  st.session_state["v2_confirmed_groups_snapshot"] = {
      p: list(proj_map.get(p, [])) for p in current_selected_non_empty
  }
  st.session_state["v2_selection_dirty"] = False
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
  st.session_state["v2_spec_dirty"] = False

if st.session_state.get("v2_selection_dirty", False):
  render_app_header(compact=True)
  if not current_selected_non_empty:
    st.info(
        "👈 当前未选择任何共用项目。请在左侧**「共用待生成项目 / 参数组」**中选择项目，然后点击 **「🚀 生成 / 更新所选项目图表」**。"
    )
  else:
    st.warning(
        f"👈 检测到共用项目或通道列选择已变更（当前已选 {len(current_selected_non_empty)} 个项目：{', '.join(current_selected_non_empty)}）。已暂停自动出图，请点击左侧 **「🚀 生成 / 更新所选项目图表」** 开始生成。"
    )
  st.stop()

confirmed_projects = [
    p
    for p in st.session_state.get("v2_confirmed_projects", [])
    if p in available_proj_names and len(proj_map.get(p, [])) > 0
]

if not confirmed_projects:
  render_app_header(compact=True)
  st.info(
      "👈 请在左侧**「共用待生成项目 / 参数组」**中选择至少一个项目，然后点击 **「🚀 生成 / 更新所选项目图表」**。"
  )
  st.stop()

# ==================== 2. 共用 SPEC 规格设定（草稿暂存，点按钮统一更新） ====================
st.sidebar.header("2️⃣ 共用 SPEC 规格设定")
st.sidebar.caption("多批次共用同一规格；修改时不实时刷新图表，点上方按钮统一生效")

current_focus_proj = st.sidebar.selectbox(
    "当前编辑 SPEC 的共用项目",
    options=confirmed_projects,
    index=0,
    key=f"v2_focus_spec_proj_{dataset_key}",
)
focus_key = f"{dataset_key}::{current_focus_proj}"
cur_draft_spec = draft_specs_map.setdefault(
    focus_key, dict(specs_map[focus_key])
)

sc1, sc2, sc3 = st.sidebar.columns(3)
lsl_w_key = f"v2_num_lsl_{focus_key}"
tgt_w_key = f"v2_num_target_{focus_key}"
usl_w_key = f"v2_num_usl_{focus_key}"

sc1.number_input(
    "LSL",
    value=float(cur_draft_spec["lsl"]),
    format="%.4f",
    key=lsl_w_key,
    on_change=_sync_v2_draft_spec,
    args=(focus_key, "lsl", lsl_w_key),
)
sc2.number_input(
    "Target",
    value=float(cur_draft_spec["target"]),
    format="%.4f",
    key=tgt_w_key,
    on_change=_sync_v2_draft_spec,
    args=(focus_key, "target", tgt_w_key),
)
sc3.number_input(
    "USL",
    value=float(cur_draft_spec["usl"]),
    format="%.4f",
    key=usl_w_key,
    on_change=_sync_v2_draft_spec,
    args=(focus_key, "usl", usl_w_key),
)

if float(draft_specs_map[focus_key]["lsl"]) >= float(
    draft_specs_map[focus_key]["usl"]
):
  st.sidebar.warning(f"⚠️ [{current_focus_proj}] LSL 应小于 USL，生效前请修正。")

if st.session_state.get("v2_spec_dirty", False):
  st.sidebar.info("SPEC 已修改待生效：请点击上方「🚀 生成 / 更新所选项目图表」")

if st.sidebar.button(
    f"🔄 重新自动估算 [{current_focus_proj}] 共用 SPEC",
    key=f"v2_btn_reest_spec_{focus_key}",
    use_container_width=True,
):
  rl, rt, ru = compute_recommended_spec_multi(
      batch_entries, proj_map[current_focus_proj], merged_spec_info
  )
  draft_specs_map[focus_key] = {"lsl": rl, "target": rt, "usl": ru}
  st.session_state[lsl_w_key] = rl
  st.session_state[tgt_w_key] = rt
  st.session_state[usl_w_key] = ru
  st.session_state["v2_spec_dirty"] = True
  st.rerun()

if len(confirmed_projects) > 1:
  with st.sidebar.expander("📋 批量查看/修改全部共用项目 SPEC", expanded=False):
    for p_name in confirmed_projects:
      pk = f"{dataset_key}::{p_name}"
      d_sp = draft_specs_map.setdefault(pk, dict(specs_map[pk]))
      st.caption(f"**{p_name}**")
      b1, b2, b3 = st.columns(3)
      bl_k = f"v2_batch_lsl_{pk}"
      bt_k = f"v2_batch_tgt_{pk}"
      bu_k = f"v2_batch_usl_{pk}"
      b1.number_input(
          "LSL",
          value=float(d_sp["lsl"]),
          format="%.4f",
          key=bl_k,
          on_change=_sync_v2_draft_spec,
          args=(pk, "lsl", bl_k),
      )
      b2.number_input(
          "Target",
          value=float(d_sp["target"]),
          format="%.4f",
          key=bt_k,
          on_change=_sync_v2_draft_spec,
          args=(pk, "target", bt_k),
      )
      b3.number_input(
          "USL",
          value=float(d_sp["usl"]),
          format="%.4f",
          key=bu_k,
          on_change=_sync_v2_draft_spec,
          args=(pk, "usl", bu_k),
      )

# ==================== 3. 全局统一样本屏蔽（单点极端尖峰屏蔽 + 行规则） ====================
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
    key=f"v2_spike_mode_{dataset_key}",
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
      key=f"v2_mad_mult_{dataset_key}",
  )
  spike_action = sp_c2.selectbox(
      "异常点处理方式",
      options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
      index=0,
      key=f"v2_sp_act_mad_{dataset_key}",
  )
elif spike_mode == "按各项目 SPEC 公差倍数识别":
  sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
  spike_param_val = sp_c1.number_input(
      "公差跨度倍数",
      min_value=1.0,
      max_value=50.0,
      value=3.0,
      step=0.5,
      key=f"v2_tol_mult_{dataset_key}",
  )
  spike_action = sp_c2.selectbox(
      "异常点处理方式",
      options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
      index=0,
      key=f"v2_sp_act_tol_{dataset_key}",
  )
elif spike_mode == "自定义单点有效数值区间":
  sp_c1, sp_c2 = st.sidebar.columns(2)
  pt_min_val = sp_c1.number_input(
      "单点最小值",
      value=float(active_ref_lsl - (active_ref_usl - active_ref_lsl)),
      format="%.4f",
      key=f"v2_pt_min_{dataset_key}",
  )
  pt_max_val = sp_c2.number_input(
      "单点最大值",
      value=float(active_ref_usl + (active_ref_usl - active_ref_lsl)),
      format="%.4f",
      key=f"v2_pt_max_{dataset_key}",
  )
  spike_action = sp_c2.selectbox(
      "异常点处理方式",
      options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
      index=0,
      key=f"v2_sp_act_rng_{dataset_key}",
  )
else:
  spike_action = "置空该单元格（保留行内其他列）"

exclude_ranges_str = st.sidebar.text_input(
    "屏蔽行号区间（支持多段，各批次同步）",
    value="",
    placeholder="例如: 1-250, 600-630",
    key=f"v2_excl_rows_{dataset_key}",
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


filter_mode = st.sidebar.selectbox(
    "行均值数值筛选规则",
    options=[
        "不屏蔽（保留全部行）",
        "按各项目 SPEC 范围过滤",
        "按自定义范围过滤（超出设定区间屏蔽）",
    ],
    index=1,
    key=f"v2_filter_mode_{dataset_key}",
)

custom_min, custom_max = None, None
if filter_mode == "按自定义范围过滤（超出设定区间屏蔽）":
  c_min, c_max = st.sidebar.columns(2)
  custom_min = c_min.number_input(
      "允许最小值",
      value=float(active_ref_lsl),
      format="%.4f",
      key=f"v2_c_min_{dataset_key}",
  )
  custom_max = c_max.number_input(
      "允许最大值",
      value=float(active_ref_usl),
      format="%.4f",
      key=f"v2_c_max_{dataset_key}",
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


# ==================== 4. 西格玛 / CPK 波动校准 ====================
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 西格玛 / CPK 波动校准", expanded=False):
  sigma_target_proj = st.selectbox(
      "校准作用项目",
      options=["当前聚焦项目"] + confirmed_projects,
      index=0,
      key=f"v2_sig_proj_{dataset_key}",
  )
  sigma_target_batch = st.selectbox(
      "校准作用批次范围",
      options=["全部对比批次"] + [b["label"] for b in batch_entries],
      index=0,
      key=f"v2_sig_batch_{dataset_key}",
  )
  enable_sigma_tuning = st.checkbox(
      "启用西格玛美化校准（全图与导出表同步）",
      value=False,
      key=f"v2_en_sig_{dataset_key}",
  )
  tuning_mode = st.radio(
      "校准方式",
      options=["直接指定目标西格玛 (σ)", "按目标 CPK 自动推算西格玛"],
      index=0,
      key=f"v2_tun_mode_{dataset_key}",
  )
  center_align_pct = st.slider(
      "均值向 Target 居中比例 (%)",
      min_value=0,
      max_value=100,
      value=0,
      step=5,
      key=f"v2_ctr_pct_{dataset_key}",
  )
  if tuning_mode == "直接指定目标西格玛 (σ)":
    manual_target_sigma = st.number_input(
        "目标组内西格玛 (Target Within σ)",
        min_value=0.000001,
        value=0.020000,
        format="%.6f",
        key=f"v2_man_sig_{dataset_key}",
    )
    target_cpk_goal = 1.33
  else:
    manual_target_sigma = None
    target_cpk_goal = st.selectbox(
        "目标 CPK 标准",
        options=[1.33, 1.50, 1.67, 2.00],
        index=0,
        key=f"v2_tgt_cpk_{dataset_key}",
    )


def build_batch_project_dataset(
    df_src, batch_label, p_name, proj_cols, p_lsl, p_target, p_usl
):
  """针对单个批次与单个项目组执行尖峰屏蔽、行过滤、西格玛校准与 SPC 计算"""
  valid_cols = [c for c in proj_cols if c in df_src.columns]
  if not valid_cols:
    return None

  excl_set = parse_exclude_indices(exclude_ranges_str, len(df_src))
  df_w = df_src.copy()
  sub_raw = df_w[valid_cols].to_numpy(dtype=float)
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
    for idx_c, c_name in enumerate(valid_cols):
      df_w[c_name] = cleaned[:, idx_c]

  df_w["_Row_Mean_"] = df_w[valid_cols].mean(axis=1)

  m_not_nan = df_w["_Row_Mean_"].notna()
  m_not_rng = ~df_w["Row_Index"].isin(excl_set)
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
  df_r = df_src[~v_mask].copy().reset_index(drop=True)

  s_mat_raw = df_c[valid_cols].to_numpy(dtype=float)
  v_vals_raw = s_mat_raw[~np.isnan(s_mat_raw)]
  if len(v_vals_raw) < 2:
    return None

  orig_m = float(np.mean(v_vals_raw))
  orig_wi = compute_within_std(s_mat_raw, v_vals_raw)

  proj_match = (
      sigma_target_proj == "当前聚焦项目" and p_name == current_focus_proj
  ) or (sigma_target_proj == p_name)
  batch_match = (sigma_target_batch == "全部对比批次") or (
      sigma_target_batch == batch_label
  )

  if enable_sigma_tuning and proj_match and batch_match and orig_wi > 0:
    adj_mean = orig_m + (p_target - orig_m) * (center_align_pct / 100.0)
    if tuning_mode == "直接指定目标西格玛 (σ)" and manual_target_sigma is not None:
      tgt_wi = float(manual_target_sigma)
    else:
      min_dist = min(p_usl - adj_mean, adj_mean - p_lsl)
      tgt_wi = (
          min_dist / (3.0 * target_cpk_goal) if min_dist > 0 else orig_wi
      )
    ratio = tgt_wi / orig_wi
    for c_name in valid_cols:
      df_c[c_name] = adj_mean + (df_c[c_name] - orig_m) * ratio
    df_c["_Row_Mean_"] = df_c[valid_cols].mean(axis=1)

  s_mat = df_c[valid_cols].to_numpy(dtype=float)
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
      "batch_label": batch_label,
      "cols": valid_cols,
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


# bundles[project_name][batch_label] = bundle_dict
bundles_by_project = {}
for p_name in confirmed_projects:
  pk = f"{dataset_key}::{p_name}"
  sp = specs_map[pk]
  if sp["lsl"] >= sp["usl"]:
    continue
  p_batch_map = {}
  for b_entry in batch_entries:
    res = build_batch_project_dataset(
        b_entry["df_raw"],
        b_entry["label"],
        p_name,
        proj_map[p_name],
        sp["lsl"],
        sp["target"],
        sp["usl"],
    )
    if res is not None:
      p_batch_map[b_entry["label"]] = res
  if p_batch_map:
    bundles_by_project[p_name] = p_batch_map

if not bundles_by_project:
  st.error(
      "当前筛选条件下，各批次有效数据点不足 2 个或 SPEC 无效，请调整后点击「生成 / 更新所选项目图表」。"
  )
  st.stop()

ready_projects = list(bundles_by_project.keys())
batch_labels_all = [b["label"] for b in batch_entries]

# ==================== 主界面头部、外边框与标题自定义 ====================
render_app_header(compact=True)

top_bar1, top_bar2 = st.columns([3.5, 1.2])
with top_bar1:
  with st.expander("✏️ 自定义对比图 / 报告主标题", expanded=False):
    title_proj_sel = st.selectbox(
        "选择项目", options=ready_projects, key=f"v2_t_proj_{dataset_key}"
    )
    k_cmp = f"v2_t_cmp_{dataset_key}_{title_proj_sel}"
    k_cap = f"v2_t_cap_{dataset_key}_{title_proj_sel}"
    k_box = f"v2_t_box_{dataset_key}_{title_proj_sel}"
    k_mean = f"v2_t_mean_{dataset_key}_{title_proj_sel}"
    st.session_state.setdefault(k_cmp, f"{title_proj_sel} — 多批次过程分布与 CPK 对比")
    st.session_state.setdefault(k_cap, f"{title_proj_sel} — Process Capability Report")
    st.session_state.setdefault(k_box, f"{title_proj_sel} — Box Plot")
    st.session_state.setdefault(k_mean, f"{title_proj_sel}均值对比")
    c_t1, c_t2 = st.columns(2)
    c_t1.text_input("多批次分布对比图标题", key=k_cmp)
    c_t2.text_input("单批次能力报告标题前缀", key=k_cap)
    c_t3, c_t4 = st.columns(2)
    c_t3.text_input("箱线图标题前缀", key=k_box)
    c_t4.text_input("多批次均值趋势图标题", key=k_mean)

with top_bar2:
  show_outer_border = st.checkbox(
      "🖼️ 图像浅灰外边框",
      value=True,
      key=f"v2_show_border_{dataset_key}",
      help="为导出图片添加浅灰色矩形边框，方便粘贴至 PPT 多图排版对齐",
  )


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


BATCH_COLORS = ["#2563EB", "#D97706", "#059669", "#7C3AED", "#DB2777"]


# ==================== 多批次绘图函数 ====================
def render_multi_batch_comparison_plot(p_name, p_batch_dict, title_str):
  """左侧多批次正态分布与箱线对比，右侧 CPK / PPK / 均值 / σ 横向对比"""
  active_labels = [lbl for lbl in batch_labels_all if lbl in p_batch_dict]
  first_b = p_batch_dict[active_labels[0]]
  p_lsl, p_target, p_usl = first_b["lsl"], first_b["target"], first_b["usl"]

  fig = plt.figure(figsize=(12.2, 6.2), dpi=170)
  gs = fig.add_gridspec(1, 2, width_ratios=[2.2, 1.25], wspace=0.25)
  ax_dist = fig.add_subplot(gs[0, 0])
  ax_kpi = fig.add_subplot(gs[0, 1])

  span = max(p_usl - p_lsl, 1e-6)
  all_concat = np.concatenate(
      [p_batch_dict[lbl]["all_valid_vals"] for lbl in active_labels]
  )
  x_min = min(p_lsl - 0.15 * span, float(np.min(all_concat)) - 0.05 * span)
  x_max = max(p_usl + 0.15 * span, float(np.max(all_concat)) + 0.05 * span)
  x_grid = np.linspace(x_min, x_max, 400)

  for idx, lbl in enumerate(active_labels):
    b = p_batch_dict[lbl]
    col = BATCH_COLORS[idx % len(BATCH_COLORS)]
    s_ov = b["std_overall"]
    if s_ov > 1e-12:
      ax_dist.plot(
          x_grid,
          stats.norm.pdf(x_grid, b["sample_mean"], s_ov),
          color=col,
          lw=2.0,
          label=f"{lbl} (CPK={b['cpk']:.2f}, μ={b['sample_mean']:.3f})",
      )
    ax_dist.axvline(b["sample_mean"], color=col, ls=":", lw=1.1, alpha=0.8)

  ax_dist.axvline(p_lsl, color="#DC2626", ls="--", lw=1.3)
  ax_dist.axvline(p_usl, color="#DC2626", ls="--", lw=1.3)
  ax_dist.axvline(p_target, color="#16A34A", ls="-.", lw=1.1)

  y_top = ax_dist.get_ylim()[1]
  ax_dist.text(
      p_lsl,
      y_top * 0.98,
      f"LSL {p_lsl}",
      color="#B91C1C",
      ha="center",
      va="top",
      fontsize=8.2,
      fontweight="bold",
  )
  ax_dist.text(
      p_usl,
      y_top * 0.98,
      f"USL {p_usl}",
      color="#B91C1C",
      ha="center",
      va="top",
      fontsize=8.2,
      fontweight="bold",
  )
  ax_dist.text(
      p_target,
      y_top * 0.98,
      f"Tgt {p_target}",
      color="#15803D",
      ha="center",
      va="top",
      fontsize=8.2,
  )

  ax_dist.set_title(
      "各批次正态分布与中心偏移对比",
      fontsize=10.5,
      fontproperties=FONT_PROP,
  )
  ax_dist.set_xlabel("测量值", fontsize=9.5, fontproperties=FONT_PROP)
  ax_dist.set_ylabel("概率密度", fontsize=9.5, fontproperties=FONT_PROP)
  ax_dist.legend(prop=FONT_PROP, fontsize=8.0, loc="upper left")
  ax_dist.grid(True, ls=":", alpha=0.45)

  # 右侧 CPK 与 PPK 分组柱状图
  x_pos = np.arange(len(active_labels))
  bar_w = 0.34
  cpk_vals = [p_batch_dict[lbl]["cpk"] for lbl in active_labels]
  ppk_vals = [p_batch_dict[lbl]["ppk"] for lbl in active_labels]

  bars1 = ax_kpi.bar(
      x_pos - bar_w / 2,
      cpk_vals,
      width=bar_w,
      color="#2563EB",
      label="CPK (组内)",
  )
  bars2 = ax_kpi.bar(
      x_pos + bar_w / 2,
      ppk_vals,
      width=bar_w,
      color="#93C5FD",
      edgecolor="#1D4ED8",
      label="PPK (整体)",
  )
  ax_kpi.axhline(1.33, color="#16A34A", ls="--", lw=1.1, label="基准 1.33")
  ax_kpi.axhline(1.00, color="#DC2626", ls=":", lw=1.0, label="警戒 1.00")

  for br in list(bars1) + list(bars2):
    h_val = br.get_height()
    if np.isfinite(h_val):
      ax_kpi.text(
          br.get_x() + br.get_width() / 2,
          h_val + 0.03,
          f"{h_val:.2f}",
          ha="center",
          va="bottom",
          fontsize=7.8,
      )

  ax_kpi.set_xticks(x_pos)
  ax_kpi.set_xticklabels(
      [lbl.split(":")[0] for lbl in active_labels],
      fontsize=8.8,
      fontproperties=FONT_PROP,
  )
  ax_kpi.set_ylim(0, max(1.8, float(np.nanmax(cpk_vals + ppk_vals)) * 1.22))
  ax_kpi.set_title("各批次过程能力指数对比", fontsize=10.5, fontproperties=FONT_PROP)
  ax_kpi.legend(prop=FONT_PROP, fontsize=7.6, loc="upper right")
  ax_kpi.grid(True, axis="y", ls=":", alpha=0.45)

  fig.suptitle(
      title_str,
      fontsize=13,
      fontweight="bold",
      y=0.98,
      fontproperties=FONT_PROP,
  )
  plt.tight_layout(rect=[0, 0, 1, 0.93])
  return save_fig_with_border(fig, use_tight=True)


def render_multi_batch_mean_trend(p_name, p_batch_dict, title_str):
  """各批次行均值变化曲线同图对比（按各自有效样本序号 1..N）"""
  active_labels = [lbl for lbl in batch_labels_all if lbl in p_batch_dict]
  first_b = p_batch_dict[active_labels[0]]
  p_lsl, p_target, p_usl = first_b["lsl"], first_b["target"], first_b["usl"]

  fig, ax = plt.subplots(figsize=(12.8, 5.4), dpi=170)
  max_len = 1
  for idx, lbl in enumerate(active_labels):
    y_m = p_batch_dict[lbl]["df_clean"]["_Row_Mean_"].to_numpy(dtype=float)
    x_s = np.arange(1, len(y_m) + 1)
    max_len = max(max_len, len(y_m))
    ax.plot(
        x_s,
        y_m,
        color=BATCH_COLORS[idx % len(BATCH_COLORS)],
        lw=1.8,
        alpha=0.88,
        label=lbl,
    )

  ax.axhline(
      p_usl, color="#DC2626", ls="--", lw=1.2, label=f"USL ({p_usl})"
  )
  ax.axhline(
      p_target, color="#16A34A", ls="-.", lw=1.1, label=f"Target ({p_target})"
  )
  ax.axhline(
      p_lsl, color="#DC2626", ls="--", lw=1.2, label=f"LSL ({p_lsl})"
  )

  ax.set_xlim(1, max(2, max_len))
  ax.set_title(
      title_str, fontsize=12.5, fontweight="bold", fontproperties=FONT_PROP
  )
  ax.set_xlabel(
      "有效样本序号 (1..N)", fontsize=9.5, fontproperties=FONT_PROP
  )
  ax.set_ylabel("行均值", fontsize=9.5, fontproperties=FONT_PROP)
  ax.grid(True, ls=":", alpha=0.45)
  ax.legend(prop=FONT_PROP, fontsize=8.2, ncol=min(5, len(active_labels) + 3))
  plt.tight_layout()
  return save_fig_with_border(fig, use_tight=True)


def render_single_batch_capability_plot(b, title_str):
  fig = plt.figure(figsize=(9.6, 7.2), dpi=170)
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
  x_grid = np.linspace(x_min_c, x_max_c, 500)

  line_ov, line_wi = None, None
  if s_ov > 1e-12:
    (line_ov,) = ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, s_mean, s_ov),
        color="#B91C1C",
        lw=1.8,
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
  ax_mid.grid(True, axis="x", ls=":", alpha=0.45)

  ax_mid.text(
      p_lsl,
      y_peak * 1.16,
      f"LSL\n{p_lsl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=8.2,
      fontweight="bold",
  )
  ax_mid.text(
      p_usl,
      y_peak * 1.16,
      f"USL\n{p_usl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=8.2,
      fontweight="bold",
  )
  ax_mid.text(
      p_target,
      y_peak * 1.16,
      f"Target\n{p_target:.2f}",
      color="#15803D",
      ha="center",
      va="bottom",
      fontsize=8.2,
  )

  left_text = (
      f"Process Data\n----------------------\n"
      f"LSL          {p_lsl:.4f}\nTarget       {p_target:.4f}\nUSL          {p_usl:.4f}\n"
      f"Mean         {s_mean:.4f}\nSample N     {tot_n}\nValid Rows   {len(b['df_clean'])}\n"
      f"Subgroup     {len(b['cols'])}\nStDev(Ov)    {s_ov:.5f}\nStDev(Wi)    {s_wi:.5f}"
  )
  ax_left.text(
      0.95,
      0.96,
      left_text,
      transform=ax_left.transAxes,
      va="top",
      ha="right",
      fontsize=8.2,
      fontfamily="monospace",
      color="#1E293B",
  )

  right_text = (
      f"Overall Capability\n------------------\n"
      f"Pp        {b['pp']:.2f}\nPPL       {b['ppl']:.2f}\nPPU       {b['ppu']:.2f}\nPpk       {b['ppk']:.2f}\n\n"
      f"Potential (Within)\n------------------\n"
      f"Cp        {b['cp']:.2f}\nCPL       {b['cpl']:.2f}\nCPU       {b['cpu']:.2f}\nCpk       {b['cpk']:.2f}"
  )
  ax_right.text(
      0.06,
      0.96,
      right_text,
      transform=ax_right.transAxes,
      va="top",
      ha="left",
      fontsize=8.2,
      fontfamily="monospace",
      color="#1E293B",
  )

  handles_leg = [h for h in (line_ov, line_wi) if h is not None]
  if handles_leg:
    ax_bot_right.legend(
        handles=handles_leg,
        loc="upper left",
        bbox_to_anchor=(0.04, 0.98),
        fontsize=8.2,
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
      fontsize=7.8,
      fontfamily="monospace",
      color="#1E293B",
      bbox=dict(
          boxstyle="round,pad=0.4", facecolor="#F8FAFC", edgecolor="#E2E8F0"
      ),
  )

  fig.suptitle(
      title_str,
      fontsize=13,
      fontweight="bold",
      y=0.96,
      fontproperties=FONT_PROP,
  )
  plt.subplots_adjust(left=0.025, right=0.975, top=0.835, bottom=0.045)
  return save_fig_with_border(fig, use_tight=False)


def render_single_batch_box_plot(b, title_str, show_outliers=False):
  fig, ax = plt.subplots(figsize=(9.6, 6.4), dpi=170)
  df_c = b["df_clean"]
  p_cols = b["cols"]
  p_lsl, p_target, p_usl = b["lsl"], b["target"], b["usl"]

  box_data = [
      arr if len(arr) > 0 else np.array([p_target], dtype=float)
      for arr in (df_c[c].dropna().to_numpy(dtype=float) for c in p_cols)
  ]
  ax.boxplot(
      box_data,
      tick_labels=[str(c) for c in p_cols],
      patch_artist=True,
      showfliers=show_outliers,
      widths=0.4,
      boxprops=dict(facecolor="#78A2CC", edgecolor="#2B4C7E", linewidth=1.0),
      medianprops=dict(color="#111827", linewidth=1.3),
  )
  ax.axhline(p_usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(p_target, color="#16A34A", ls=":", lw=1.1)
  ax.axhline(p_lsl, color="#DC2626", ls="--", lw=1.2)
  ax.set_title(
      title_str,
      fontsize=12.5,
      fontweight="bold",
      pad=10,
      fontproperties=FONT_PROP,
  )
  ax.tick_params(axis="x", rotation=35 if len(p_cols) > 5 else 0, labelsize=8.5)
  for lbl in ax.get_xticklabels():
    lbl.set_fontproperties(FONT_PROP)
  ax.grid(True, ls=":", alpha=0.45)
  plt.tight_layout()
  return save_fig_with_border(fig, use_tight=False)


# ==================== 多批次总览对比表 + 一键打包 ZIP ====================
st.subheader("多批次指标横向对比总览")
cmp_rows = []
for p_name in ready_projects:
  for b_lbl in batch_labels_all:
    b = bundles_by_project[p_name].get(b_lbl)
    if b is None:
      continue
    cmp_rows.append({
        "项目组": p_name,
        "批次": b_lbl,
        "有效行数": len(b["df_clean"]),
        "总样本 N": b["total_n"],
        "屏蔽单点": b["masked_cells"],
        "LSL": b["lsl"],
        "Target": b["target"],
        "USL": b["usl"],
        "均值": round(b["sample_mean"], 4),
        "组内σ": round(b["std_within"], 5),
        "CPK": round(b["cpk"], 2),
        "PPK": round(b["ppk"], 2),
        "实测PPM": round(b["obs_total"], 1),
    })

st.dataframe(pd.DataFrame(cmp_rows), width="stretch", hide_index=True)

zip_buf = io.BytesIO()
with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
  for p_name in ready_projects:
    safe_p = re.sub(r'[\\/*?:"<>|]', "_", p_name)
    t_cmp = str(
        st.session_state.get(
            f"v2_t_cmp_{dataset_key}_{p_name}", f"{p_name} — 多批次对比"
        )
    )
    zf.writestr(
        f"{safe_p}/{safe_p}_多批次分布与CPK对比.png",
        render_multi_batch_comparison_plot(
            p_name, bundles_by_project[p_name], t_cmp
        ).getvalue(),
    )
    for b_lbl, b_obj in bundles_by_project[p_name].items():
      safe_b = re.sub(r'[\\/*?:"<>|]', "_", b_lbl)
      zf.writestr(
          f"{safe_p}/{safe_b}/{safe_p}_{safe_b}_CPK.png",
          render_single_batch_capability_plot(
              b_obj, f"{p_name} [{b_lbl}] — Process Capability Report"
          ).getvalue(),
      )
zip_buf.seek(0)
st.download_button(
    "下载",
    data=zip_buf,
    file_name="v2.0_多批次SPC对比图表包.zip",
    mime="application/zip",
    key=f"v2_dl_zip_{dataset_key}",
)

# ==================== 按共用项目分标签页展示 ====================
proj_tabs = st.tabs([f"📊 {p_name}" for p_name in ready_projects])

for p_tab, p_name in zip(proj_tabs, ready_projects):
  with p_tab:
    p_batch_map = bundles_by_project[p_name]
    available_b_labels = [lbl for lbl in batch_labels_all if lbl in p_batch_map]
    safe_p = re.sub(r'[\\/*?:"<>|]', "_", p_name)

    t_cmp_default = f"{p_name} — 多批次过程分布与 CPK 对比"
    t_cap_default = f"{p_name} — Process Capability Report"
    t_box_default = f"{p_name} — Box Plot"
    t_mean_default = f"{p_name}均值对比"

    t_cmp = str(
        st.session_state.get(f"v2_t_cmp_{dataset_key}_{p_name}", t_cmp_default)
        or t_cmp_default
    )
    t_cap_prefix = str(
        st.session_state.get(f"v2_t_cap_{dataset_key}_{p_name}", t_cap_default)
        or t_cap_default
    )
    t_box_prefix = str(
        st.session_state.get(f"v2_t_box_{dataset_key}_{p_name}", t_box_default)
        or t_box_default
    )
    t_mean_title = str(
        st.session_state.get(
            f"v2_t_mean_{dataset_key}_{p_name}", t_mean_default
        )
        or t_mean_default
    )

    sub_cmp, sub_single, sub_data = st.tabs([
        "1️⃣ 多批次联合对比图",
        "2️⃣ 单批次明细图表（逐批检查）",
        "3️⃣ 各批次清洗明细导出",
    ])

    with sub_cmp:
      buf_cmp = render_multi_batch_comparison_plot(p_name, p_batch_map, t_cmp)
      st.image(buf_cmp, width=980)
      render_chart_action_bar(
          buf_cmp, f"{safe_p}_MultiBatch_Compare.png", f"cmp_{dataset_key}_{p_name}"
      )

      st.markdown("---")
      buf_mt = render_multi_batch_mean_trend(
          p_name, p_batch_map, t_mean_title
      )
      st.image(buf_mt, width=1020)
      render_chart_action_bar(
          buf_mt,
          f"{safe_p}_MultiBatch_MeanTrend.png",
          f"mt_{dataset_key}_{p_name}",
      )

    with sub_single:
      chosen_b_lbl = st.selectbox(
          "选择要查看完整 SPC 图表的批次",
          options=available_b_labels,
          key=f"v2_pick_batch_{dataset_key}_{p_name}",
      )
      b_cur = p_batch_map[chosen_b_lbl]
      safe_b = re.sub(r'[\\/*?:"<>|]', "_", chosen_b_lbl)

      sc_left, sc_right = st.columns(2)
      with sc_left:
        buf_b_cap = render_single_batch_capability_plot(
            b_cur, f"{t_cap_prefix} [{chosen_b_lbl}]"
        )
        st.image(buf_b_cap, width=640)
        render_chart_action_bar(
            buf_b_cap,
            f"{safe_p}_{safe_b}_CPK.png",
            f"bcap_{dataset_key}_{p_name}_{chosen_b_lbl}",
        )
      with sc_right:
        show_out_b = st.checkbox(
            "显示异常点",
            value=False,
            key=f"v2_bout_{dataset_key}_{p_name}_{chosen_b_lbl}",
        )
        buf_b_box = render_single_batch_box_plot(
            b_cur, f"{t_box_prefix} [{chosen_b_lbl}]", show_outliers=show_out_b
        )
        st.image(buf_b_box, width=640)
        render_chart_action_bar(
            buf_b_box,
            f"{safe_p}_{safe_b}_Box.png",
            f"bbox_{dataset_key}_{p_name}_{chosen_b_lbl}",
        )

    with sub_data:
      excel_buf = io.BytesIO()
      with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        for b_lbl in available_b_labels:
          sh_name = re.sub(r'[\\/*?:\[\]]', "_", b_lbl)[:31]
          p_batch_map[b_lbl]["df_clean"].to_excel(
              writer, sheet_name=sh_name, index=False
          )
      excel_buf.seek(0)
      st.download_button(
          "下载",
          data=excel_buf,
          file_name=f"{safe_p}_各批次有效数据.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          key=f"v2_dl_xlsx_{dataset_key}_{p_name}",
      )
      for b_lbl in available_b_labels:
        st.caption(f"**{b_lbl}**（有效行：{len(p_batch_map[b_lbl]['df_clean'])}）")
        st.dataframe(p_batch_map[b_lbl]["df_clean"], width="stretch")