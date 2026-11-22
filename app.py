import os
import time
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from scanner_core import (run_scan_full, send_telegram, build_alert_message,
                          build_alert_message_v2)
import historico

st.set_page_config(
    page_title="B3 Pivot Scanner Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",  # melhor no celular
)


# ==================== SEGREDOS (fora do código) ====================
def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, "")


TELEGRAM_TOKEN = get_secret("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# Disparo do workflow do GitHub pelo botão (opcional)
GH_TOKEN = get_secret("GH_TOKEN")                       # token do GitHub com permissão Actions: write
GH_REPO = get_secret("GH_REPO") or "Leandro-Bascka/Reversoes_pivot_Bascka"
GH_WORKFLOW = get_secret("GH_WORKFLOW") or "scanner.yml"
GH_REF = get_secret("GH_REF") or "main"
HISTORICO = "data/historico_sinais.csv"


def disparar_workflow(enviar_todos: bool):
    """Dispara o workflow no GitHub Actions. Retorna (ok, mensagem)."""
    import requests
    token = str(GH_TOKEN).strip().strip("\"'")
    if not token:
        return False, "Falta o segredo GH_TOKEN nos Secrets do Streamlit."
    try:
        r = requests.post(
            f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{GH_WORKFLOW}/dispatches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": GH_REF, "inputs": {"todos": enviar_todos}},
            timeout=15,
        )
    except Exception as e:
        return False, f"Erro de conexão com o GitHub ({type(e).__name__})."
    if r.status_code == 204:
        return True, "Workflow iniciado. O resultado chega no Telegram em 2 a 5 minutos."
    dicas = {
        401: "Token inválido ou expirado.",
        403: "O token não tem permissão 'Actions: write' neste repositório.",
        404: "Repositório ou arquivo do workflow não encontrado (ou o token não enxerga o repositório).",
        422: "O branch está errado, ou o workflow não tem 'workflow_dispatch'.",
    }
    return False, f"GitHub respondeu {r.status_code}. {dicas.get(r.status_code, '')}"


TIPOS = {
    "Dois sinais: antecipado e confirmado (recomendado)": "dois",
    "Só antecipados (mais cedo, mais falsos sinais)": "antecipado",
    "Só confirmados (mais confiável)": "confirmado",
}
GRUPOS_MAX = {"Estrutura": 25, "Liquidez/SMC": 20, "Volume/Fluxo": 15,
              "Momentum": 15, "Tendência/Médias": 15, "Mercado": 10}

# ==================== INTERFACE ====================
st.title("🎯 B3 Pivot Scanner Pro")
st.caption("Pivôs + estrutura de fundos/topos + Bascka Reversal V2 (SMC, fluxo, semanal, IBOV, stop e alvos), "
           "nas ações mais líquidas")

with st.sidebar:
    st.header("Configurações")
    top_n = st.slider("Analisar as N ações mais líquidas", 10, 80, 30, 5,
                      help="A lista atual tem cerca de 58 ativos; acima disso, só entram os que existirem na lista.")
    min_vol_mi = st.slider("Volume mínimo (R$ milhões)", 3.0, 25.0, 8.0, 1.0)
    enviar_telegram = st.checkbox("Enviar alertas no Telegram", value=True)

    st.markdown("---")
    st.subheader("Bascka Reversal V2")
    usar_v2 = st.checkbox("Ativar a camada V2", value=True)
    perfil = st.selectbox("Perfil de entrada", ["Equilibrado", "Conservador", "Agressivo"],
                          help="Conservador: score ≥ 75, só confirmadas/reteste e semanal não contrário. "
                               "Equilibrado: score ≥ 60. Agressivo: score ≥ 45, inclui antecipadas.")
    tipo_label = st.selectbox("Tipo de sinal", list(TIPOS))
    tipo = TIPOS[tipo_label]

    st.markdown("---")
    st.subheader("Pivôs (lógica original)")
    min_score = st.slider("Score mínimo", 5, 12, 6)
    left = st.slider("Left", 3, 10, 5)
    right = st.slider("Right", 2, 6, 3)
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

with st.expander("📲 Rodar o scanner no GitHub e receber no Telegram"):
    enviar_todos_gh = st.checkbox("Enviar todos os sinais atuais (e não só os novos)", value=True)
    if st.button("▶️ Disparar workflow do GitHub"):
        agora = time.time()
        if agora - st.session_state.get("ultimo_disparo", 0) < 60:
            st.warning("Aguarde 1 minuto entre um disparo e outro.")
        else:
            ok, msg = disparar_workflow(enviar_todos_gh)
            if ok:
                st.session_state["ultimo_disparo"] = agora
                st.success(msg)
            else:
                st.error(msg)
    st.caption(f"Acompanhe a execução em https://github.com/{GH_REPO}/actions")

with st.expander("ℹ️ Como ler os sinais"):
    st.markdown(
        "**Modalidades de entrada (V2)**\n"
        "- **Antecipada:** Liquidity Sweep (o pavio perfura o fundo e o preço fecha de volta acima) com sinal de perda de "
        "força vendedora. É um alerta de oportunidade, não uma reversão confirmada.\n"
        "- **Confirmada:** o preço fecha acima do topo estrutural (CHoCH) com volume. É a preferencial.\n"
        "- **Reteste:** depois do rompimento, o preço volta à região rompida e sustenta.\n\n"
        "**Score V2 (0 a 100):** Estrutura 25 · Liquidez/SMC 20 · Volume/Fluxo 15 · Momentum 15 · "
        "Tendência/Médias 15 · Mercado 10. Pesos iniciais, para testes: não são probabilidades de acerto. "
        "Score alto sem rompimento estrutural nunca vira \"confirmada\".\n\n"
        "**Estágios (estrutura):** 1·Aviso (fundo mais baixo com divergência) · 2·Virada (fundo ascendente) · "
        "3·Confirmada (fechamento acima do topo da recuperação)."
    )

if st.button("🚀 Rodar Análise Completa", type="primary", width="stretch"):
    progress = st.progress(0)
    status = st.empty()

    def cb(i, total, n_sinais):
        progress.progress(i / total)
        status.text(f"Processando {i}/{total} | Sinais: {n_sinais}")

    out = run_scan_full(
        left=left, right=right, min_vol=min_vol_mi * 1_000_000,
        min_score=min_score, top_n=top_n, progress_cb=cb, perfil=perfil, tipo=tipo, usar_v2=usar_v2,
        struct={
            "n_pivots": n_pivots, "tol": tol_pct / 100, "min_move_atr": min_move_atr,
            "exigir_topos": exigir_topos, "exigir_estrutura": exigir_estrutura,
        },
    )
    progress.empty()
    status.empty()
    st.session_state["out"] = out

    df1, df2 = out["v1"], out["v2"]
    n1 = 0 if df1 is None else len(df1)
    n2 = 0 if df2 is None else len(df2)
    if n1 + n2 == 0:
        st.warning("Nenhum sinal encontrado com os filtros atuais.")
    else:
        st.success(f"✅ V2: {n2} sinais · Pivôs: {n1} sinais, entre as {len(out['ranking'])} mais líquidas")
    if usar_v2 and not out.get("ibov_ok"):
        st.info("Não consegui baixar o IBOV agora: o contexto de mercado ficou neutro nesta análise.")

    if enviar_telegram:
        enviados = []
        if df2 is not None:
            novos2 = df2[df2["Novo"] & (df2["Modo"] != "—")]
            for i in range(0, len(novos2), 5):
                send_telegram(build_alert_message_v2(novos2.iloc[i:i + 5].to_dict("records"),
                                                     "Bascka Reversal V2 — novos sinais"),
                              TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
            if len(novos2):
                enviados.append(f"{len(novos2)} V2")
        if df1 is not None:
            fortes = df1[df1["Alerta"].str.contains("FORTE")]
            if not fortes.empty:
                ok = send_telegram(
                    build_alert_message(fortes.to_dict("records"), "Alertas Fortes"),
                    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                )
                if ok:
                    enviados.append(f"{len(fortes)} fortes (pivôs)")
                else:
                    st.warning("Não consegui enviar ao Telegram (verifique os segredos).")
        if enviados:
            st.info("📤 Enviado ao Telegram: " + " e ".join(enviados))

# ==================== RESULTADOS ====================
out = st.session_state.get("out")
if out:
    if out["ranking"]:
        with st.expander(f"💧 Universo analisado: {len(out['ranking'])} mais líquidas"):
            for i, (t, v) in enumerate(out["ranking"], 1):
                st.write(f"{i}. **{t.replace('.SA', '')}**: R$ {v/1e6:,.1f} mi/dia")

    tab2, tab1, tab3 = st.tabs(["🎯 Reversal V2", "📌 Pivôs (original)", "📒 Histórico"])

    # ---------------- V2 ----------------
    with tab2:
        df2 = out["v2"]
        if df2 is None:
            st.info("Nenhum sinal V2 com o perfil e o tipo escolhidos.")
        else:
            cols = ["Ticker", "Direção", "Modo", "Classe", "Score V2", "Estágio", "Semanal", "Entrada",
                    "Stop", "Alvo 1", "Alvo 2", "Alvo 3", "Stop %", "R/R estrutural", "Liq Rank", "Novo"]
            st.dataframe(df2[cols], width="stretch", height=380)

            opc = [f"{r['Ticker']} | {r['Direção']} | {r['Modo']} | Score {r['Score V2']}" for _, r in df2.iterrows()]
            esc = st.selectbox("Selecione o sinal", opc, key="sel_v2")
            row = df2.iloc[opc.index(esc)]
            res, d = row["_res"], row["_df"]

            m = st.columns(5)
            m[0].metric("Entrada", f"R$ {row['Entrada']}")
            m[1].metric("Stop", f"R$ {row['Stop']}", f"-{row['Stop %']}%", delta_color="off")
            m[2].metric("Alvo 1 (1,5R)", f"R$ {row['Alvo 1']}")
            m[3].metric("Alvo 2 (2R)", f"R$ {row['Alvo 2']}")
            m[4].metric("Alvo 3 (3R)", f"R$ {row['Alvo 3']}")
            st.caption(f"{row['Classe']} · Semanal: {row['Semanal']} · Pivô em {row['Data pivô']} "
                       f"(confirmado em {row['Confirmado em']}) · Sinal desde {row['Sinal desde']}")
            if row["Stop %"] > 12:
                st.warning(f"Stop distante ({row['Stop %']}% do preço): o risco por operação fica alto.")

            c1, c2 = st.columns([1, 1])
            with c1:
                gf = go.Figure(go.Bar(
                    x=[res["grupos"][k] for k in GRUPOS_MAX], y=list(GRUPOS_MAX), orientation="h",
                    text=[f"{res['grupos'][k]:.0f}/{GRUPOS_MAX[k]}" for k in GRUPOS_MAX], textposition="auto"))
                gf.update_layout(height=260, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10),
                                 title="Score por grupo", yaxis=dict(autorange="reversed"),
                                 xaxis=dict(range=[0, 25]))
                st.plotly_chart(gf, width="stretch")
            with c2:
                st.markdown("**Evidências**")
                for e in res["evidencias"]:
                    st.write("• " + e)

            dd = d.tail(260)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.03)
            fig.add_trace(go.Candlestick(x=dd.index, open=dd["Open"], high=dd["High"], low=dd["Low"],
                                         close=dd["Close"], name="Preço"), row=1, col=1)
            fig.add_trace(go.Scatter(x=dd.index, y=dd["EMA20"], line=dict(color="orange", width=1), name="EMA20"), row=1, col=1)
            fig.add_trace(go.Scatter(x=dd.index, y=dd["EMA50"], line=dict(color="royalblue", width=1), name="EMA50"), row=1, col=1)
            fig.add_hline(y=row["Entrada"], line_color="white", line_dash="dot", row=1, col=1, annotation_text="Entrada")
            fig.add_hline(y=row["Stop"], line_color="red", line_dash="dash", row=1, col=1, annotation_text="Stop")
            for k_, nome in enumerate(("Alvo 1", "Alvo 2", "Alvo 3")):
                fig.add_hline(y=row[nome], line_color="lime", line_dash="dot", row=1, col=1,
                              annotation_text=nome, opacity=0.6)
            if row["Nível"] is not None and pd.notna(row["Nível"]):
                fig.add_hline(y=row["Nível"], line_color="yellow", line_dash="dot", row=1, col=1,
                              annotation_text="Topo estrutural", annotation_position="top left")
            if res["ob"]:
                fig.add_hrect(y0=res["ob"][0], y1=res["ob"][1], fillcolor="rgba(0,150,255,0.18)",
                              line_width=0, row=1, col=1, annotation_text="Order Block")
            if res["fvg"]:
                fig.add_hrect(y0=res["fvg"][0], y1=res["fvg"][1], fillcolor="rgba(255,200,0,0.15)",
                              line_width=0, row=1, col=1, annotation_text="FVG")
            piv = d.index[res["idx_pivo"]]
            if piv in dd.index:
                y_p = d.loc[piv, "Low"] if res["direcao"] == "Compra" else d.loc[piv, "High"]
                fig.add_trace(go.Scatter(x=[piv], y=[y_p], mode="markers", name="Pivô estrutural",
                                         marker=dict(symbol="triangle-up" if res["direcao"] == "Compra" else "triangle-down",
                                                     size=14, color="lime" if res["direcao"] == "Compra" else "red")),
                              row=1, col=1)
            if res["sweep"] and res["sweep_barras"] is not None:
                sw_i = d.index[len(d) - 1 - res["sweep_barras"]]
                if sw_i in dd.index:
                    y_s = d.loc[sw_i, "Low"] if res["direcao"] == "Compra" else d.loc[sw_i, "High"]
                    fig.add_trace(go.Scatter(x=[sw_i], y=[y_s], mode="markers+text", text=["Sweep"],
                                             textposition="bottom center", name="Liquidity Sweep",
                                             marker=dict(symbol="x", size=12, color="magenta")), row=1, col=1)
            cores = ["green" if c >= o else "red" for o, c in zip(dd["Open"], dd["Close"])]
            fig.add_trace(go.Bar(x=dd.index, y=dd["Volume"], marker_color=cores, showlegend=False), row=2, col=1)
            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False,
                              margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, width="stretch")

    # ---------------- Pivôs (original) ----------------
    with tab1:
        df = out["v1"]
        if df is None:
            st.info("Nenhum sinal de pivô com os filtros atuais.")
        else:
            st.subheader("Sinais Encontrados")
            show = df[["Ticker", "Alerta", "Estágio", "Liq Rank", "Preço Pivô", "Preço Atual", "Nível",
                       "Dias", "Vol Rel", "RSI", "Divergência", "Score"]]
            st.dataframe(show, width="stretch", height=400)

            st.subheader("Análise Gráfica")
            opcoes = [f"{r['Ticker']} | {r['Alerta']} | {r['Estágio']} | Score {r['Score']}" for _, r in df.iterrows()]
            escolha = st.selectbox("Selecione o sinal", opcoes, key="sel_v1")

            if escolha:
                row = df.iloc[opcoes.index(escolha)]
                d = row["_df"].tail(260)

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
                                    vertical_spacing=0.03)
                fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"],
                                             low=d["Low"], close=d["Close"], name="Preço"), row=1, col=1)

                full = row["_df"]
                if row["_tipo"] == "low":
                    fig.add_trace(go.Scatter(x=[row["_idx"]], y=[full.loc[row["_idx"], "Low"]],
                                             mode="markers", marker=dict(symbol="triangle-up", size=15, color="lime"),
                                             name="Pivot Low"), row=1, col=1)
                else:
                    fig.add_trace(go.Scatter(x=[row["_idx"]], y=[full.loc[row["_idx"], "High"]],
                                             mode="markers", marker=dict(symbol="triangle-down", size=15, color="red"),
                                             name="Pivot High"), row=1, col=1)

                if pd.notna(row["Nível"]):
                    fig.add_hline(y=row["Nível"], line_dash="dot", line_color="yellow", row=1, col=1,
                                  annotation_text="Nível de confirmação", annotation_position="top left")

                fig.add_trace(go.Scatter(x=d.index, y=d["EMA20"], line=dict(color="orange", width=1), name="EMA20"), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d["EMA50"], line=dict(color="blue", width=1), name="EMA50"), row=1, col=1)

                colors = ["green" if c >= o else "red" for o, c in zip(d["Open"], d["Close"])]
                fig.add_trace(go.Bar(x=d.index, y=d["Volume"], marker_color=colors, showlegend=False), row=2, col=1)

                fig.update_layout(height=560, template="plotly_dark", xaxis_rangeslider_visible=False,
                                  margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig, width="stretch")

    # ---------------- Histórico ----------------
    with tab3:
        hist = historico.carregar(HISTORICO)
        if hist.empty:
            st.info("Ainda não há sinais registrados. O histórico é gravado pelo job automático do GitHub "
                    "(data/historico_sinais.csv) e aparece aqui depois do primeiro registro.")
        else:
            st.dataframe(hist.sort_values("data_sinal", ascending=False), width="stretch", height=380)
            st.markdown("**Resultado dos sinais já encerrados** (R = múltiplos do risco; "
                        "entrada na abertura seguinte, stop vence se tocado junto com o alvo, custos descontados)")
            st.dataframe(historico.resumo(hist), width="stretch", hide_index=True)
