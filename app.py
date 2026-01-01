import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- 設定網頁配置 (必須在第一行) ---
st.set_page_config(
    page_title="台股戰情室",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📈"
)

# --- CSS 樣式優化 (黑底、大字體) ---
st.markdown("""
    <style>
    .stApp {
        background-color: #000000;
        color: white;
    }
    h1, h2, h3, p, div {
        color: white !important;
    }
    /* 調整按鈕樣式 */
    .stButton>button {
        width: 100%;
        border: 1px solid white;
        background-color: #333;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. 數據獲取與指標計算函數 ---
@st.cache_data(ttl=60)  # 設定緩存 60 秒，避免頻繁請求
def get_stock_data(ticker_symbol):
    # 下載數據 (最近 3 個月，間隔 1 天，若要更即時可改 interval='5m' 但需考慮 API 限制)
    df = yf.download(ticker_symbol, period="3mo", interval="1d", progress=False)
    
    if df.empty:
        return None

    # 整理欄位 (Yahoo Finance 有時會有多層索引)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # --- 計算技術指標 ---
    # 1. MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']

    # 2. KD (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    
    # 遞迴計算 K 與 D (比較慢但準確)
    k_values = [50]
    d_values = [50]
    for i in range(1, len(df)):
        rsv = df['RSV'].iloc[i]
        if pd.isna(rsv): rsv = 50
        k = (2/3) * k_values[-1] + (1/3) * rsv
        d = (2/3) * d_values[-1] + (1/3) * k
        k_values.append(k)
        d_values.append(d)
    
    df['K'] = k_values
    df['D'] = d_values

    return df

# --- 2. 繪圖函數 (Plotly) ---
def plot_chart(df, title):
    if df is None:
        st.error(f"無法獲取 {title} 數據")
        return

    # 建立 4 列的子圖 (K線, VOL, KD, MACD)
    fig = make_subplots(
        rows=4, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.02, 
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=(f"{title} 走勢", "成交量", "KD", "MACD")
    )

    # 顏色定義 (台灣: 紅漲綠跌)
    color_up = '#ff3333'
    color_down = '#00cc00'

    # --- K線圖 (Row 1) ---
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        increasing_line_color=color_up, decreasing_line_color=color_down, name='Price'
    ), row=1, col=1)

    # --- 成交量 (Row 2) ---
    colors_vol = [color_up if c >= o else color_down for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(
        x=df.index, y=df['Volume'], marker_color=colors_vol, name='Volume'
    ), row=2, col=1)

    # --- KD 線 (Row 3) ---
    fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='orange', width=1), name='K'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='cyan', width=1), name='D'), row=3, col=1)
    # 增加 80/20 參考線
    fig.add_hline(y=80, line_dash="dot", line_color="gray", row=3, col=1)
    fig.add_hline(y=20, line_dash="dot", line_color="gray", row=3, col=1)

    # --- MACD (Row 4) ---
    fig.add_trace(go.Bar(
        x=df.index, y=df['Hist'], 
        marker_color=[color_up if x >= 0 else color_down for x in df['Hist']], 
        name='MACD Hist'
    ), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='yellow', width=1), name='MACD'), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='blue', width=1), name='Signal'), row=4, col=1)

    # --- 版面設定 ---
    fig.update_layout(
        template='plotly_dark',
        height=600,  # 圖表總高度
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis_rangeslider_visible=False
    )
    
    # 移除子圖間的格線干擾
    fig.update_xaxes(showgrid=True, gridcolor='#333')
    fig.update_yaxes(showgrid=True, gridcolor='#333')

    st.plotly_chart(fig, use_container_width=True)

# --- 3. 主程式介面 ---

# 頂部按鈕區
col_btn1, col_btn2 = st.columns([8, 2])
with col_btn1:
    st.title("台股即時儀表板")
with col_btn2:
    if st.button("🔄 SS (重整)"):
        st.cache_data.clear() # 清除緩存以獲取最新數據
        st.rerun()

# 顯示最後更新時間
st.caption(f"最後更新: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

st.markdown("---")

# 區塊 1: 加權指數
st.subheader("🏛️ 加權指數 (TSE)")
with st.spinner('載入加權指數數據...'):
    df_tse = get_stock_data("^TWII")
    if df_tse is not None:
        # 顯示最新報價
        last_close = df_tse['Close'].iloc[-1]
        prev_close = df_tse['Close'].iloc[-2]
        change = last_close - prev_close
        pct = (change / prev_close) * 100
        color = "red" if change > 0 else "green"
        st.markdown(f"<h2 style='color:{color}; text-align:center'>{last_close:,.0f} <small>({change:+.0f} / {pct:+.2f}%)</small></h2>", unsafe_allow_html=True)
        
        plot_chart(df_tse, "加權指數")

st.markdown("---")

# 區塊 2: 台指期 (近月)
# 注意: Yahoo Finance 的台指期代號通常是 WTX=F (代表連續月)
st.subheader("⚡ 台指期 (近月)")
with st.spinner('載入台指期數據...'):
    df_future = get_stock_data("WTX=F") # 或是使用 TIW=F
    if df_future is not None:
         # 顯示最新報價
        last_close_f = df_future['Close'].iloc[-1]
        prev_close_f = df_future['Close'].iloc[-2]
        change_f = last_close_f - prev_close_f
        pct_f = (change_f / prev_close_f) * 100
        color_f = "red" if change_f > 0 else "green"
        st.markdown(f"<h2 style='color:{color_f}; text-align:center'>{last_close_f:,.0f} <small>({change_f:+.0f} / {pct_f:+.2f}%)</small></h2>", unsafe_allow_html=True)

        plot_chart(df_future, "台指期連續月")
    else:
        st.warning("無法讀取台指期數據 (WTX=F)，可能是盤後或數據源暫時中斷。")
