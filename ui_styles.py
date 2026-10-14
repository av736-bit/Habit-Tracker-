"""Compact, understated Streamlit CSS for a productivity dashboard."""


def apply_styles(st, mode: str) -> None:
    dark = mode == "Dark"
    bg = "#0c111b" if dark else "#f6f8fc"
    panel = "#151c2a" if dark else "#ffffff"
    sidebar = "#101726" if dark else "#edf2f8"
    fg = "#e6ebf5" if dark else "#172033"
    subtle = "#9da8bb" if dark else "#64748b"
    line = "#293348" if dark else "#dde4ee"
    hover = "#1d2939" if dark else "#e9eef7"
    st.markdown(f"""
    <style>
    :root {{ color-scheme: {'dark' if dark else 'light'}; }}
    .stApp, [data-testid="stAppViewContainer"] {{ background: {bg} !important; color: {fg}; }}
    [data-testid="stHeader"] {{ background: {bg} !important; }}
    [data-testid="stSidebar"], [data-testid="stSidebarContent"] {{ background: {sidebar} !important; }}
    h1, h2, h3, h4, p, label, .stMarkdown, [data-testid="stMetricLabel"], [data-testid="stMetricValue"] {{ color: {fg} !important; }}
    .stCaption, [data-testid="stCaptionContainer"] p {{ color: {subtle} !important; }}
    [data-testid="stVerticalBlockBorderWrapper"] > div, [data-testid="stExpander"] {{
        border-color: {line} !important;
        border-radius: 14px !important;
    }}
    input, textarea, [data-baseweb="select"] > div, [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div, [data-baseweb="base-input"] {{
        background: {panel} !important; color: {fg} !important; border-color: {line} !important;
    }}
    [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {{ background: {panel} !important; color: {fg} !important; }}
    .stButton button, .stFormSubmitButton button {{ border-radius: 10px !important; }}
    [data-testid="stMetric"] {{ background: {panel}; border: 1px solid {line}; border-radius: 14px; padding: 16px 18px; }}
    .block-container {{ max-width: 1160px !important; padding-top: 2rem !important; padding-bottom: 4rem !important; }}
    .momentum-eyebrow {{ color: #5b93e5 !important; letter-spacing: .16em; text-transform: uppercase; font-size: 11px; font-weight: 700; }}
    .momentum-subtitle {{ color: {subtle} !important; font-size: 15px; margin-bottom: 18px; }}
    .momentum-card {{ background: {panel}; border: 1px solid {line}; border-radius: 16px; padding: 17px 19px; margin: 6px 0 12px; }}
    .momentum-card .title {{ color: {fg} !important; font-size: 16px; font-weight: 650; }}
    .momentum-card .meta {{ color: {subtle} !important; font-size: 12px; margin-top: 4px; }}
    .momentum-brand {{ font-size: 23px; letter-spacing: -.04em; font-weight: 780; color: {fg} !important; margin: 8px 0 2px; }}
    .momentum-pill {{ border: 1px solid {line}; border-radius: 100px; padding: 4px 10px; font-size: 11px; color: {subtle}; }}
    [data-testid="stSidebar"] .stRadio label {{ border-radius: 9px; padding: 2px; }}
    [data-testid="stSidebar"] .stRadio label:hover {{ background: {hover}; }}
    </style>
    """, unsafe_allow_html=True)
