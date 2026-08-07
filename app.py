# app.py — 像素镜界 Streamlit 应用
# 回答 7 个问题，AI 为你绘制专属像素世界 + 心灵映照报告

import json
import html
import re
import random
import logging
import base64
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from config import Q6_SIZE_MAP, Q6_SHAPE_MAP, THEME
from lib.errors import DashScopeError
from lib.dashscope_text import generate_prompt, generate_report
from lib.dashscope_image import generate_image, download_image
from lib.sensitive import filter_sensitive_words
from lib.storage import upload_image, save_submission, get_submissions, is_supabase_configured

# ===== 数据加载 =====

_DATA_DIR = Path(__file__).parent / "data"


def _load_json(filename: str) -> dict:
    with open(_DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


QUESTIONS = _load_json("questions.json")["questions"]
FALLBACK_NAMES = _load_json("fallback-names.json")["names"]

TOTAL_STEPS = 9  # 0=API Key, 1-7=Q1-Q7, 8=Consent


# ===== Session State =====

def init_state():
    defaults = {
        "page": "home",
        "step": 0,
        "answers": {},
        "api_key": "",
        "result": None,
        "error": None,
        "consent_choice": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_questionnaire():
    """重置问卷状态"""
    st.session_state.step = 0
    st.session_state.answers = {}
    st.session_state.error = None
    st.session_state.consent_choice = None


# ===== CSS =====

def inject_css():
    css_vars = "\n".join(f"        --{k}: {v};" for k, v in THEME.items())

    st.markdown(f"""
    <style>
    /* ===== CSS 变量（源自 config.py THEME） ===== */
    :root {{
{css_vars}
    }}

    /* ===== 全局背景（纯黑 + 赛博网格） ===== */
    .stApp {{
        background-color: var(--bg_base);
    }}
    .stApp::before {{
        content: '';
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        background-image:
            linear-gradient(rgba(255, 16, 240, 0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(57, 255, 20, 0.06) 1px, transparent 1px);
        background-size: 40px 40px;
        pointer-events: none;
        z-index: 0;
    }}
    /* 扫描线覆盖层 */
    .stApp::after {{
        content: '';
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        background: repeating-linear-gradient(
            0deg,
            rgba(0, 0, 0, 0.12) 0px,
            rgba(0, 0, 0, 0.12) 1px,
            transparent 1px,
            transparent 3px
        );
        pointer-events: none;
        z-index: 9998;
        animation: y2k-flicker 0.15s infinite;
    }}
    @keyframes y2k-flicker {{
        0%   {{ opacity: 0.97; }}
        50%  {{ opacity: 1.0; }}
        100% {{ opacity: 0.98; }}
    }}

    /* ===== 侧边栏 ===== */
    .stSidebar > div:first-child {{
        background-color: var(--bg_panel);
        border-right: 2px solid var(--accent_pink);
        box-shadow: 0 0 15px rgba(255, 16, 240, 0.3);
    }}

    /* ===== 主按钮（霓虹粉光泽） ===== */
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg,
            var(--accent_pink) 0%,
            #ff44ff 30%,
            var(--accent_pink) 60%,
            #cc00cc 100%);
        color: var(--bg_base);
        border: 2px solid var(--accent_pink);
        border-radius: 6px;
        box-shadow:
            0 0 10px rgba(255, 16, 240, 0.6),
            0 0 20px rgba(255, 16, 240, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
        font-family: monospace;
        font-weight: bold;
        text-shadow: 0 0 2px rgba(0, 0, 0, 0.5);
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden;
    }}
    .stButton > button[kind="primary"]::before {{
        content: '';
        position: absolute;
        top: 0; left: 0;
        width: 100%; height: 50%;
        background: linear-gradient(to bottom,
            rgba(255, 255, 255, 0.25), transparent);
        pointer-events: none;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: linear-gradient(135deg,
            #ff44ff 0%, var(--accent_pink) 50%, #cc00cc 100%);
        box-shadow:
            0 0 15px rgba(255, 16, 240, 0.8),
            0 0 30px rgba(255, 16, 240, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 0.4);
        transform: translateY(-1px);
    }}
    .stButton > button[kind="primary"]:active {{
        transform: translateY(1px);
        box-shadow: 0 0 5px rgba(255, 16, 240, 0.5);
    }}

    /* ===== 次要按钮（霓虹绿轮廓） ===== */
    .stButton > button[kind="secondary"] {{
        background: transparent;
        color: var(--accent_green);
        border: 2px solid var(--accent_green);
        border-radius: 6px;
        box-shadow:
            0 0 8px rgba(57, 255, 20, 0.3),
            inset 0 0 8px rgba(57, 255, 20, 0.05);
        font-family: monospace;
        transition: all 0.2s ease;
    }}
    .stButton > button[kind="secondary"]:hover {{
        background: rgba(57, 255, 20, 0.1);
        border-color: var(--accent_green);
        color: var(--accent_green);
        box-shadow:
            0 0 15px rgba(57, 255, 20, 0.5),
            inset 0 0 12px rgba(57, 255, 20, 0.1);
    }}
    .stButton > button[kind="secondary"]:active {{
        transform: translateY(1px);
    }}

    /* ===== 文本输入框 ===== */
    .stTextInput > div > div > input {{
        background-color: var(--bg_card);
        border: 2px solid var(--accent_pink);
        border-radius: 4px;
        color: var(--text_primary);
        font-family: monospace;
        box-shadow: 0 0 8px rgba(255, 16, 240, 0.2);
    }}
    .stTextInput > div > div > input:focus {{
        border-color: var(--accent_green);
        box-shadow: 0 0 12px rgba(57, 255, 20, 0.4);
    }}

    /* ===== 文字颜色 ===== */
    .stMarkdown, .stText {{
        color: var(--text_primary);
    }}

    /* ===== 标题（霓虹粉辉光） ===== */
    h1, h2, h3 {{
        color: var(--accent_pink) !important;
        font-family: monospace;
        text-shadow:
            0 0 5px var(--accent_pink),
            0 0 10px var(--accent_pink),
            0 0 20px rgba(255, 16, 240, 0.5);
    }}

    /* ===== 进度条（霓虹绿辉光） ===== */
    .stProgress > div > div > div {{
        background: linear-gradient(90deg, var(--accent_green), #88ff66);
        box-shadow: 0 0 10px rgba(57, 255, 20, 0.6);
    }}

    /* ===== 容器间距 ===== */
    [data-testid="stVerticalBlock"] {{
        gap: 0.75rem;
    }}

    /* ===== 像素装饰 ===== */
    .pixel-deco {{
        display: flex;
        gap: 4px;
        justify-content: center;
        margin: 16px 0;
    }}
    .pixel-deco span {{
        display: inline-block;
        width: 12px;
        height: 12px;
        box-shadow: 0 0 6px currentColor;
    }}

    /* ===== 特性卡片（Y2K 金属面板） ===== */
    .feature-card {{
        background: linear-gradient(145deg,
            var(--bg_card) 0%, var(--bg_panel) 100%);
        border: 2px solid var(--accent_pink);
        border-radius: 8px;
        box-shadow:
            0 0 12px rgba(255, 16, 240, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.05);
        padding: 16px;
        text-align: center;
        position: relative;
        overflow: hidden;
    }}
    .feature-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0;
        width: 100%; height: 40%;
        background: linear-gradient(to bottom,
            rgba(255, 255, 255, 0.08), transparent);
        pointer-events: none;
    }}
    .feature-card .num {{
        color: var(--accent_green);
        font-family: monospace;
        font-size: 14px;
        font-weight: bold;
        text-shadow: 0 0 6px var(--accent_green);
    }}
    .feature-card .label {{
        color: var(--text_primary);
        font-size: 14px;
        margin-top: 8px;
    }}

    /* ===== 选项按钮 ===== */
    .option-btn {{
        background: var(--bg_card);
        border: 2px solid var(--accent_pink);
        border-radius: 6px;
        box-shadow: 0 0 8px rgba(255, 16, 240, 0.2);
        padding: 16px;
        margin-bottom: 12px;
        cursor: pointer;
        transition: all 0.2s ease;
    }}
    .option-btn:hover {{
        background: var(--bg_hover);
        border-color: var(--accent_green);
        box-shadow: 0 0 12px rgba(57, 255, 20, 0.4);
    }}

    /* ===== Y2K 通用面板类 ===== */
    .y2k-panel {{
        background: linear-gradient(145deg,
            var(--bg_card) 0%, var(--bg_panel) 100%);
        border: 2px solid var(--accent_pink);
        border-radius: 8px;
        box-shadow:
            0 0 12px rgba(255, 16, 240, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.05);
        padding: 24px;
        position: relative;
        overflow: hidden;
    }}
    .y2k-panel::before {{
        content: '';
        position: absolute;
        top: 0; left: 0;
        width: 100%; height: 40%;
        background: linear-gradient(to bottom,
            rgba(255, 255, 255, 0.08), transparent);
        pointer-events: none;
    }}
    .y2k-heading {{
        color: var(--accent_pink);
        text-shadow:
            0 0 5px var(--accent_pink),
            0 0 10px var(--accent_pink);
    }}
    .y2k-subtitle {{
        color: var(--text_secondary);
    }}
    .y2k-report-title {{
        color: var(--accent_green);
        text-shadow: 0 0 5px var(--accent_green);
    }}
    .y2k-text {{
        color: var(--text_primary);
    }}

    /* ===== 隐藏 Streamlit 默认元素 ===== */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    header[data-testid="stHeader"] {{ visibility: hidden; }}

    /* ===== 滚动条（霓虹粉） ===== */
    ::-webkit-scrollbar {{
        width: 8px;
    }}
    ::-webkit-scrollbar-track {{
        background: var(--bg_base);
    }}
    ::-webkit-scrollbar-thumb {{
        background: var(--accent_pink);
        border-radius: 4px;
        box-shadow: 0 0 6px var(--accent_pink);
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: #ff44ff;
    }}

    /* ===== 选中文字 ===== */
    ::selection {{
        background: var(--accent_pink);
        color: var(--bg_base);
    }}
    </style>
    """, unsafe_allow_html=True)


# ===== 导航 =====

def go_to(page: str):
    st.session_state.page = page
    st.rerun()


# ===== 像素装饰 HTML =====

def pixel_deco(top=True):
    colors = [THEME["accent_pink"], THEME["accent_green"]] * 4
    if not top:
        colors = [THEME["accent_green"], THEME["accent_pink"]] * 4
    squares = "".join(
        f'<span style="background:{c}; color:{c};"></span>' for c in colors[:7]
    )
    st.markdown(f'<div class="pixel-deco">{squares}</div>', unsafe_allow_html=True)


# ===== 首页 =====

def render_home():
    col_spacer1, col_main, col_spacer2 = st.columns([1, 3, 1])
    with col_main:
        pixel_deco(top=True)

        st.markdown(
            '<h1 class="y2k-heading" style="text-align:center; font-size:3rem;">'
            '像素镜界'
            '</h1>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<p class="y2k-subtitle" style="text-align:center; font-size:1.1rem;">'
            '回答 7 个问题，AI 将为你绘制一个专属的像素世界，<br>'
            '并附上一段只属于你的心灵映照报告。'
            '</p>',
            unsafe_allow_html=True,
        )

        st.write("")

        # 特性卡片
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                '<div class="feature-card">'
                '<div class="num">01</div>'
                '<div class="label">沉浸式问卷</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                '<div class="feature-card">'
                '<div class="num">02</div>'
                '<div class="label">AI 像素生成</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                '<div class="feature-card">'
                '<div class="num">03</div>'
                '<div class="label">心灵映照</div>'
                '</div>',
                unsafe_allow_html=True,
            )

        st.write("")

        # 开始按钮
        col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 2])
        with col_btn2:
            if st.button("开始创造", type="primary", use_container_width=True):
                reset_questionnaire()
                go_to("create")

        st.write("")
        pixel_deco(top=False)


# ===== 创造页（问卷）=====

def render_create():
    col_spacer1, col_main, col_spacer2 = st.columns([1, 4, 1])
    with col_main:
        step = st.session_state.step

        # 进度条
        st.progress((step + 1) / TOTAL_STEPS, text=f"步骤 {step + 1} / {TOTAL_STEPS}")

        # 错误信息
        if st.session_state.error:
            st.error(st.session_state.error)
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                if st.button("重试", type="primary", use_container_width=True):
                    st.session_state.error = None
                    if st.session_state.consent_choice is not None:
                        do_generate(st.session_state.consent_choice)
            with col_e2:
                if st.button("返回修改", type="secondary", use_container_width=True):
                    st.session_state.error = None
                    st.session_state.step = max(0, step - 1)
                    st.rerun()
            return

        # ===== Step 0: API Key =====
        if step == 0:
            st.markdown(
                '<h3 class="y2k-heading">准备出发</h3>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="y2k-subtitle">'
                '首先，请输入你的百炼 API Key，用于驱动 AI 生成。'
                '</p>',
                unsafe_allow_html=True,
            )

            api_key = st.text_input(
                "百炼 API Key",
                type="password",
                value=st.session_state.api_key,
                placeholder="请输入百炼平台 API Key（适用于 qwen 系列模型）",
            )
            st.session_state.api_key = api_key

            st.caption(
                "可在 [百炼控制台](https://bailian.console.aliyun.com/) 获取 API Key"
            )

            st.write("")
            if st.button("开始问卷", type="primary", use_container_width=True):
                if not api_key.strip():
                    st.error("请输入 API Key")
                else:
                    st.session_state.step = 1
                    st.rerun()

        # ===== Steps 1-6: 选择题 =====
        elif 1 <= step <= 6:
            q = QUESTIONS[step - 1]
            st.markdown(
                f'<h3 class="y2k-heading">{q["title"]}</h3>',
                unsafe_allow_html=True,
            )
            st.write("")

            # 显示选项为按钮
            for opt in q.get("options", []):
                opt_text = f"  {opt['id']}.  {opt['text']}"
                # 检查是否已选中
                prev_answer = st.session_state.answers.get(q["id"], "")
                is_selected = prev_answer == opt["id"]

                if st.button(
                    opt_text,
                    key=f"q{step}_{opt['id']}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                ):
                    st.session_state.answers[q["id"]] = opt["id"]
                    st.session_state.step = step + 1
                    st.rerun()

            st.write("")
            _render_back_button(step)

        # ===== Step 7: 世界名称（文本输入） =====
        elif step == 7:
            q = QUESTIONS[6]
            st.markdown(
                f'<h3 class="y2k-heading">{q["title"]}</h3>',
                unsafe_allow_html=True,
            )
            st.write("")

            prev_name = st.session_state.answers.get("Q7", "")
            world_name = st.text_input(
                "世界名称",
                value=prev_name,
                placeholder=q.get("placeholder", "给世界起个名字..."),
            )

            st.write("")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("下一步", type="primary", use_container_width=True):
                    st.session_state.answers["Q7"] = world_name
                    st.session_state.step = 8
                    st.rerun()
            with col2:
                _render_back_button(step)

        # ===== Step 8: 知情同意 =====
        elif step == 8:
            st.markdown(
                '<h3 class="y2k-heading">最后一步</h3>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="y2k-panel" style="margin:16px 0;">'
                '<p class="y2k-text" style="font-size:0.95rem;">'
                '在生成完成后，你创作的像素世界和心灵报告<b>可以</b>被保存到数据库中，'
                '用于历史记录和展示。<br><br>'
                '你的问卷选择和 API Key <b>不会</b>被存储。<br><br>'
                '是否同意保存你的创作结果？'
                '</p>'
                '</div>',
                unsafe_allow_html=True,
            )

            st.write("")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("同意并保存", type="primary", use_container_width=True):
                    st.session_state.consent_choice = True
                    do_generate(True)
            with col2:
                if st.button("仅生成（不保存）", type="secondary", use_container_width=True):
                    st.session_state.consent_choice = False
                    do_generate(False)

            st.write("")
            _render_back_button(step)

        # 返回首页
        st.write("")
        if st.button("返回首页", type="secondary", use_container_width=True):
            go_to("home")


def _render_back_button(step: int):
    """渲染返回上一步按钮"""
    if step > 0:
        if st.button("返回上一步", type="secondary", use_container_width=True):
            st.session_state.step = step - 1
            st.session_state.error = None
            st.rerun()


# ===== 生成流程 =====

def do_generate(consent: bool):
    """执行完整的生成流程：文本 → 图像 → 存储"""
    api_key = st.session_state.api_key.strip()
    answers = st.session_state.answers

    if not api_key:
        st.session_state.error = "未提供 API Key，请返回输入页面填写"
        st.rerun()
        return

    # Q7 为空则随机命名
    world_name = (answers.get("Q7", "") or "").strip()
    if not world_name:
        world_name = random.choice(FALLBACK_NAMES)

    # 敏感词过滤
    has_sensitive, words = filter_sensitive_words(world_name)
    if has_sensitive:
        st.session_state.error = "世界名称含敏感词，请修改后重新提交"
        st.rerun()
        return

    # 获取尺寸和形状
    size = Q6_SIZE_MAP.get(answers.get("Q6", ""), "1280*1280")
    shape = Q6_SHAPE_MAP.get(answers.get("Q6", ""), "square")

    try:
        # Step 1: 并行生成提示词 + 心灵报告
        with st.spinner("正在生成提示词和心灵报告（并行）..."):
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_prompt = executor.submit(
                    generate_prompt, api_key, answers, world_name
                )
                future_report = executor.submit(
                    generate_report, api_key, answers, world_name
                )
                prompt_result = future_prompt.result()
                report_result = future_report.result()

        # Step 2: 生成像素图像
        with st.spinner("正在生成像素图像..."):
            image_url = generate_image(api_key, prompt_result, size)

        # Step 3: 下载图像
        with st.spinner("正在下载图像..."):
            image_bytes = download_image(image_url)

        # Step 4: 上传到 Supabase（可选）
        with st.spinner("正在保存图像..."):
            permanent_url = upload_image(image_bytes)

        # Step 5: 保存到数据库（可选）
        submission_id = None
        if consent:
            submission_id = save_submission({
                "world_name": world_name,
                "prompt": prompt_result,
                "image_url": permanent_url,
                "image_shape": shape,
                "report": report_result,
                "consent": True,
            })

        # 存储结果
        st.session_state.result = {
            "id": submission_id,
            "world_name": world_name,
            "prompt": prompt_result,
            "image_url": permanent_url,
            "image_shape": shape,
            "report": report_result,
            "image_bytes": image_bytes,
        }
        st.session_state.error = None
        go_to("result")

    except DashScopeError as e:
        st.session_state.error = e.message
        st.rerun()
    except (KeyError, IndexError, TypeError) as e:
        logging.exception("生成结果解析失败")
        st.session_state.error = "生成结果解析失败，请重试"
        st.rerun()
    except Exception as e:
        logging.exception("do_generate 意外异常")
        st.session_state.error = "生成过程中出现意外错误，请重试"
        st.rerun()


# ===== 结果页 =====

def render_result():
    result = st.session_state.result
    if not result:
        st.error("未找到结果，请重新创建。")
        if st.button("重新创建", type="primary"):
            reset_questionnaire()
            go_to("create")
        return

    world_name = result["world_name"]
    image_bytes = result.get("image_bytes")
    image_url = result.get("image_url", "")
    image_shape = result.get("image_shape", "square")
    report = result.get("report", "")
    prompt = result.get("prompt", "")

    # 转义用户/AI 生成内容，防止 HTML 注入
    escaped_world_name = html.escape(world_name)
    escaped_report = html.escape(report)
    # 净化文件名中的非法字符
    safe_file_name = re.sub(r'[\\/:*?"<>|]', '_', world_name)

    # 标题
    st.markdown(
        f'<h1 class="y2k-heading" style="text-align:center;">{escaped_world_name}</h1>',
        unsafe_allow_html=True,
    )
    st.write("")

    # 两列布局
    col_img, col_report = st.columns([3, 2])

    with col_img:
        # 图片展示
        if image_bytes:
            if image_shape == "shard":
                # 碎片形状：使用 clip-path
                img_b64 = base64.b64encode(image_bytes).decode()
                st.markdown(
                    f'<div style="text-align:center;">'
                    f'<img src="data:image/png;base64,{img_b64}" '
                    f'style="max-width:100%; '
                    f'clip-path: polygon(20% 0%, 80% 0%, 100% 30%, 100% 70%, '
                    f'80% 100%, 20% 100%, 0% 70%, 0% 30%); '
                    f'image-rendering: pixelated;" />'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.image(image_bytes, use_container_width=True)

        st.write("")
        # 下载按钮
        st.download_button(
            label="下载像素世界",
            data=image_bytes,
            file_name=f"{safe_file_name}.png",
            mime="image/png",
            type="primary",
            use_container_width=True,
        )

    with col_report:
        # 心灵报告
        st.markdown(
            '<div class="y2k-panel" style="padding:20px; max-height:70vh; '
            'overflow-y:auto;">'
            f'<h3 class="y2k-report-title" style="margin-top:0;">镜灵箴言</h3>'
            f'<p class="y2k-text" style="white-space:pre-wrap; '
            f'line-height:1.8;">{escaped_report}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 生成提示词（折叠）
        if prompt:
            with st.expander("生成提示词"):
                st.code(prompt, language="markdown")

    st.write("")
    st.write("")

    # 导航按钮
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("返回首页", type="secondary", use_container_width=True):
            go_to("home")
    with col2:
        if st.button("再创一个", type="primary", use_container_width=True):
            reset_questionnaire()
            go_to("create")
    with col3:
        if st.button("历史记录", type="secondary", use_container_width=True):
            go_to("history")


# ===== 历史记录页 =====

def render_history():
    st.markdown(
        '<h2 class="y2k-heading">历史记录</h2>',
        unsafe_allow_html=True,
    )
    st.write("")

    if not is_supabase_configured():
        st.markdown(
            '<div class="y2k-panel" style="text-align:center;">'
            '<p class="y2k-subtitle">'
            '历史记录功能需要配置 Supabase。<br>'
            '请设置环境变量 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY 后重启应用。'
            '</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        submissions = get_submissions(limit=20)
        if not submissions:
            st.info("暂无历史记录。")
        else:
            for sub in submissions:
                col_img, col_info = st.columns([1, 3])
                with col_img:
                    img_url = sub.get("image_url", "")
                    if img_url and img_url.startswith("http"):
                        st.image(img_url, width=120)
                with col_info:
                    st.markdown(
                        f'**{sub.get("world_name", "未命名")}**',
                    )
                    st.caption(
                        f'形状：{sub.get("image_shape", "未知")} | '
                        f'创建时间：{sub.get("created_at", "未知")}'
                    )
                st.divider()

    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("返回首页", type="secondary", use_container_width=True):
            go_to("home")
    with col2:
        if st.button("再创一个", type="primary", use_container_width=True):
            reset_questionnaire()
            go_to("create")


# ===== 主函数 =====

def main():
    st.set_page_config(
        page_title="像素镜界",
        page_icon="🎮",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_state()
    inject_css()

    # 侧边栏导航
    with st.sidebar:
        st.markdown(
            '<h2 class="y2k-heading">像素镜界</h2>',
            unsafe_allow_html=True,
        )
        st.write("")

        if st.button("首页", use_container_width=True):
            go_to("home")
        if st.button("创造", use_container_width=True):
            reset_questionnaire()
            go_to("create")
        if st.button("历史记录", use_container_width=True):
            go_to("history")

        st.write("")
        st.divider()

        # 状态指示
        st.markdown("**状态**")
        api_status = "已输入" if st.session_state.api_key else "未输入"
        st.markdown(f"- API Key：{api_status}")

        supabase_status = "已配置" if is_supabase_configured() else "未配置"
        st.markdown(f"- Supabase：{supabase_status}")

        st.write("")
        st.divider()
        st.caption("Powered by 百炼 qwen3.7-plus + wan2.6-t2i")

    # 页面路由
    page = st.session_state.page
    if page == "home":
        render_home()
    elif page == "create":
        render_create()
    elif page == "result":
        render_result()
    elif page == "history":
        render_history()
    else:
        render_home()


if __name__ == "__main__":
    main()
