import os
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from scanner_core import run_scan, send_telegram, build_alert_message

st.set_page_config(
    page_title="B3 Pivot Scanner Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",  # melhor no celular
)


# ==================== TELEGRAM (segredos fora do código) ====================
def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, "")


TELEGRAM_TOKEN = get_secret("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# ==================== INTERFACE ====================
st.title("🎯 B3 Pivot Scanner Pro")
st.caption("Pivôs + estrutura de fundos/topos + volume + divergência RSI + score, nas ações mais líquidas")

with st.sidebar:
    st.header("Configurações")
    top_n = st.slider("Analisar as N ações mais líquidas", 10, 60, 30, 5)
    min_vol_mi = st.slider("Volume mínimo (R$ milhões)", 3.0, 25.0, 8.0, 1.0)
    min_score = st.slider("Score mínimo", 5, 12, 6)
    left = st.slider("Left", 3, 10, 5)
    right = st.slider("Right", 2, 6, 3)
    enviar_telegram = st.checkbox("Enviar alertas fortes no Telegram", value=True)

    st.markdown("---")
    st.subheader("Estrutura de mercado")
    n_pivots = st.slider("Fundos/topos na tendência anterior", 2, 4, 2)
    tol_pct = st.slider("Tolerância 'fundo igual' (%)", 0.0, 1.0, 0.3, 0.1)
    min_move_atr = st.slider("Movimento anterior mínimo (x ATR)", 0.5, 4.0, 1.5, 0.5)
    exigir_topos = st.checkbox("Exigir topos descendentes (e fundos ascendentes na venda)", value=True)
    exigir_estrutura = st.checkbox("Só mostrar sinais com estrutura (etapas 1 a 3)", value=True)

    st.markdown("---")
    if st.button("Testar Telegram"):
        ok = send_telegram(
            "✅ Teste de conexão do B3 Pivot Scanner realizado com sucesso!",
            TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
        )
        if ok:
            st.success("Mensagem de teste enviada!")
        else:
            st.error("Falha ao enviar. Confira TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.")

with st.expander("ℹ️ Como ler os estágios"):
    st.markdown(
        "- **1·Aviso:** novo fundo mais baixo (ou topo mais alto) com divergência no RSI. A virada ainda não começou.\n"
        "- **2·Virada:** surgiu um fundo ascendente (ou topo descendente) depois da sequência anterior.\n"
        "- **3·Confirmada:** o preço rompeu, no fechamento, o topo da recuperação (ou o fundo, na venda)."
    )

if st.button("🚀 Rodar Análise Completa", type="primary", use_container_width=True):
    progress = st.progress(0)
    status = st.empty()

    def cb(i, total, n_sinais):
        progress.progress(i / total)
        status.text(f"Processando {i}/{total} | Sinais: {n_sinais}")

    df, ranking = run_scan(
        left=left, right=right, min_vol=min_vol_mi * 1_000_000,
        min_score=min_score, top_n=top_n, progress_cb=cb,
        struct={
            "n_pivots": n_pivots, "tol": tol_pct / 100, "min_move_atr": min_move_atr,
            "exigir_topos": exigir_topos, "exigir_estrutura": exigir_estrutura,
        },
    )
    progress.empty()
    status.empty()

    st.session_state["ranking"] = ranking

    if df is None:
        st.session_state.pop("df", None)
        st.warning("Nenhum sinal encontrado com os filtros atuais.")
    else:
        st.session_state["df"] = df
        st.success(f"✅ {len(df)} sinais encontrados entre as {len(ranking)} mais líquidas")

        if enviar_telegram:
            fortes = df[df["Alerta"].str.contains("FORTE")]
            if not fortes.empty:
                ok = send_telegram(
                    build_alert_message(fortes.to_dict("records"), "Alertas Fortes"),
                    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                )
                if ok:
                    st.info(f"📤 {len(fortes)} alerta(s) forte(s) enviado(s) para o Telegram")
                else:
                    st.warning("Não consegui enviar ao Telegram (verifique os segredos).")

# ==================== RESULTADOS ====================
if "ranking" in st.session_state and st.session_state["ranking"]:
    with st.expander(f"💧 Universo analisado: {len(st.session_state['ranking'])} mais líquidas"):
        for i, (t, v) in enumerate(st.session_state["ranking"], 1):
            st.write(f"{i}. **{t.replace('.SA', '')}**: R$ {v/1e6:,.1f} mi/dia")

if "df" in st.session_state:
    df = st.session_state["df"]

    st.subheader("Sinais Encontrados")
    show = df[["Ticker", "Alerta", "Estágio", "Liq Rank", "Preço Pivô", "Preço Atual", "Nível",
               "Dias", "Vol Rel", "RSI", "Divergência", "Score"]]
    st.dataframe(show, use_container_width=True, height=400)

    st.subheader("Análise Gráfica")
    opcoes = [f"{r['Ticker']} | {r['Alerta']} | {r['Estágio']} | Score {r['Score']}" for _, r in df.iterrows()]
    escolha = st.selectbox("Selecione o sinal", opcoes)

    if escolha:
        idx_sel = opcoes.index(escolha)
        row = df.iloc[idx_sel]
        d = row["_df"]

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
                            vertical_spacing=0.03)

        fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"],
                                     low=d["Low"], close=d["Close"], name="Preço"), row=1, col=1)

        if row["_tipo"] == "low":
            fig.add_trace(go.Scatter(x=[row["_idx"]], y=[d.loc[row["_idx"], "Low"]],
                                     mode="markers", marker=dict(symbol="triangle-up", size=15, color="lime"),
                                     name="Pivot Low"), row=1, col=1)
        else:
            fig.add_trace(go.Scatter(x=[row["_idx"]], y=[d.loc[row["_idx"], "High"]],
                                     mode="markers", marker=dict(symbol="triangle-down", size=15, color="red"),
                                     name="Pivot High"), row=1, col=1)

        # Nível de confirmação da estrutura (quebra de topo/fundo)
        if pd.notna(row["Nível"]):
            fig.add_hline(y=row["Nível"], line_dash="dot", line_color="yellow", row=1, col=1,
                          annotation_text="Nível de confirmação", annotation_position="top left")

        fig.add_trace(go.Scatter(x=d.index, y=d["EMA20"], line=dict(color="orange", width=1), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=d.index, y=d["EMA50"], line=dict(color="blue", width=1), name="EMA50"), row=1, col=1)

        colors = ["green" if c >= o else "red" for o, c in zip(d["Open"], d["Close"])]
        fig.add_trace(go.Bar(x=d.index, y=d["Volume"], marker_color=colors, showlegend=False), row=2, col=1)

        fig.update_layout(height=560, template="plotly_dark", xaxis_rangeslider_visible=False,
                          margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
