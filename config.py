# config.py — 全局配置：主题色、常量、模型参数

# ===== 主题色（Y2K 千禧风：霓虹粉 / 霓虹绿 / 黑色）=====
THEME = {
    "bg_base": "#0a0a0a",
    "bg_panel": "#1a0a2e",
    "bg_card": "#16001f",
    "bg_hover": "#2a0a3e",
    "accent_pink": "#FF10F0",
    "accent_green": "#39FF14",
    "accent_chrome": "#C0C0C0",
    "accent_chrome_dark": "#808080",
    "text_primary": "#e0e0e0",
    "text_secondary": "#8888aa",
    "text_error": "#ff0066",
    "border_glow": "#FF10F0",
}

# ===== DashScope API 配置 =====
DASHSCOPE_TEXT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_IMAGE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
TEXT_MODEL = "qwen3.7-plus"
IMAGE_MODEL = "wan2.6-t2i"

# ===== 超时配置（秒）=====
TEXT_TIMEOUT = 120
IMAGE_TIMEOUT = 60
IMAGE_DOWNLOAD_TIMEOUT = 30

# ===== 文本生成参数 =====
TEXT_TEMPERATURE = 0.6
TEXT_MAX_TOKENS = 2000

# ===== 图片生成参数 =====
NEGATIVE_PROMPT = (
    "blurry, anti-aliased, smooth edges, gradients, photorealistic, "
    "3d render, oil painting, watercolor, depth of field, bokeh"
)

# ===== Q6 尺寸与形状映射 =====
Q6_SIZE_MAP = {
    "A": "1280*1280",
    "B": "1104*1472",
    "C": "1472*1104",
    "D": "1280*1280",
}

Q6_SHAPE_MAP = {
    "A": "square",
    "B": "portrait",
    "C": "landscape",
    "D": "shard",
}

# ===== Supabase 配置 =====
SUPABASE_BUCKET_NAME = "pixel-images"
