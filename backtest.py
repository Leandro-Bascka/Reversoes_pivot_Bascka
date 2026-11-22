"""Backtest walk-forward da Bascka Reversal V2.

Sem olhar o futuro: em cada pregão t o sinal é avaliado só com os candles até t (pivôs dos
últimos 'right' candles ficam de fora); a execução é na ABERTURA do pregão seguinte.
Regras de saída e custos: veja historico.py (stop vence se tocado junto com o alvo, 20 barras
no máximo, custo de 0,15% descontado em R). Cada alvo (1,5R / 2R / 3R) é uma corrida separada
entre o stop e aquele alvo.

Saídas: backtest_out/backtest_resultados.csv (operação por operação), backtest_out/backtest_resumo.md
e, no GitHub Actions, o resumo aparece na página do run. Opcionalmente manda o resumo ao Telegram.

Variáveis de ambiente (opcionais): BT_PERIODO (5y), TOP_N (0 = todos), MIN_VOL_MI (8), BT_WARMUP (210),
BT_WORKERS (3), BT_MAX_MIN (25), BT_CUSTO_PCT (0.15), BT_MIN_SCORE (40), BT_TELEGRAM (1),
BT_OUT (backtest_out), TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import numpy as np
import pandas as pd

import scanner_core as sc
import historico as H
from reversal_v2 import alinhar_mercado, V2_DEFAULT
from universo import carregar_universo, limite

PERIODO = os.environ.get("BT_PERIODO", "5y")
UNIVERSO = carregar_universo()
TOP_N = limite(os.environ.get("TOP_N", 0), UNIVERSO)   # 0 = todos os ativos da lista
MIN_VOL = float(os.environ.get("MIN_VOL_MI", 8)) * 1_000_000
WARMUP = int(os.environ.get("BT_WARMUP", 210))
WORKERS = int(os.environ.get("BT_WORKERS", 3))
MAX_MIN = float(os.environ.get("BT_MAX_MIN", 25))
CUSTO = float(os.environ.get("BT_CUSTO_PCT", 0.15))
MIN_SCORE_BT = int(os.environ.get("BT_MIN_SCORE", 40))
OUT = os.environ.get("BT_OUT", "backtest_out")
ALVOS = H.ALVOS_R
COOLDOWN = 10   # barras sem repetir a mesma modalidade no mesmo ativo/direção


# ==================== SIMULAÇÃO ====================
def bt_ticker(ticker, df, ibov, struct, p, warmup, deadline, custo):
    """Walk-forward de um ativo nas duas direções. Retorna (ticker, lista de operações)."""
    mercado = alinhar_mercado(ibov, df.index)
    n = len(df)
    o, h, l, c = (df[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    trades = []
    for direction in ("up", "down"):
        ontem, ultimo = set(), {}
        for t in range(warmup, n - 1):
            if time.time() > deadline:
                break
            res = sc.avaliar_em(df, t, direction, struct, p, mercado)
            hoje = set(res["modos"]) if res else set()
            novos = hoje - ontem
            ontem = hoje
            if not res or res["score"] < MIN_SCORE_BT:
                continue
            for m in novos:
                if t - ultimo.get(m, -999) < COOLDOWN:
                    continue
                ultimo[m] = t
                lim = min(n, t + 1 + H.MAX_BARRAS)
                r = H.resolver(o[t + 1:lim], h[t + 1:lim], l[t + 1:lim], c[t + 1:lim],
                               res["direcao"], res["stop"], custo_pct=custo)
                if r is None:
                    continue
                compra = res["direcao"] == "Compra"
                ent = r["entrada"]
                if compra:
                    ponta = l[max(0, t - 10):t + 1].min()
                    pico = h[t + 1:min(n, t + 21)].max()
                    cap = (pico - ent) / (pico - ponta) if pico > ponta else np.nan
                else:
                    ponta = h[max(0, t - 10):t + 1].max()
                    pico = l[t + 1:min(n, t + 21)].min()
                    cap = (ent - pico) / (ponta - pico) if ponta > pico else np.nan
                regime = "n/d"
                if mercado is not None and np.isfinite(mercado["EMA200"].iloc[t]):
                    regime = "IBOV acima da EMA200" if mercado["Close"].iloc[t] > mercado["EMA200"].iloc[t] \
                        else "IBOV abaixo da EMA200"
                row = {
                    "ticker": ticker.replace(".SA", ""), "data": df.index[t].strftime("%Y-%m-%d"),
                    "direcao": res["direcao"], "modo": m, "classe": res["classe"], "score": res["score"],
                    "alinhamento": res["alinhamento"], "regime": regime,
                    "entrada": round(ent, 2), "stop": res["stop"], "risco_pct": round(100 * r["risco"] / ent, 2),
                    "captura": None if not np.isfinite(cap) else round(float(np.clip(cap, 0, 1)), 3),
                }
                for k in ALVOS:
                    a = r["alvos"][k]
                    row[f"r_{k}"] = a["r"]
                    row[f"mot_{k}"] = a["motivo"]
                trades.append(row)
    return ticker, trades


# ==================== MÉTRICAS ====================
def metricas(g, k):
    """Métricas de um grupo de operações para o alvo k (só operações já encerradas)."""
    r = g[f"r_{k}"].astype(float)
    ok = r.notna()
    r = r[ok]
    if len(r) == 0:
        return {"n": 0}
    ganhos, perdas = r[r > 0].sum(), -r[r < 0].sum()
    eq = r.reset_index(drop=True).cumsum()
    dd = float((eq.cummax() - eq).max()) if len(eq) else 0.0
    return {
        "n": int(len(r)),
        "acerto": 100 * float((r > 0).mean()),
        "R_medio": float(r.mean()),
        "PF": float(ganhos / perdas) if perdas > 0 else np.inf,
        "DD_R": dd,
        "falsos": 100 * float((g.loc[ok, f"mot_{k}"] == "stop").mean()),
    }


def tabela_grupos(trades, coluna, ordem=None):
    linhas = []
    chaves = ordem or sorted(trades[coluna].dropna().unique())
    for ch in chaves:
        g = trades[trades[coluna] == ch].sort_values("data")
        if g.empty:
            continue
        lin = {coluna: ch, "n": len(g)}
        cap = g["captura"].dropna()
        lin["captura mediana %"] = None if cap.empty else round(100 * float(cap.median()), 0)
        for k in ALVOS:
            m = metricas(g, k)
            if m["n"]:
                pf = "∞" if np.isinf(m["PF"]) else f"{m['PF']:.2f}"
                lin[f"{k}R acerto%"] = round(m["acerto"], 1)
                lin[f"{k}R R médio"] = round(m["R_medio"], 2)
                lin[f"{k}R PF"] = pf
        m15 = metricas(g, ALVOS[0])
        lin["falsos% (stop antes de 1,5R)"] = round(m15["falsos"], 1) if m15["n"] else None
        lin["amostra"] = "pequena (<30)" if len(g) < 30 else "ok"
        linhas.append(lin)
    return pd.DataFrame(linhas)


def to_md(df):
    if df is None or df.empty:
        return "_sem dados_\n"
    cab = "| " + " | ".join(map(str, df.columns)) + " |\n"
    sep = "|" + "|".join(["---"] * len(df.columns)) + "|\n"
    corpo = "".join("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |\n"
                    for row in df.itertuples(index=False))
    return cab + sep + corpo


def relatorio(trades):
    faixas = pd.cut(trades["score"], [-1, 59, 74, 89, 100],
                    labels=["40-59 Observação", "60-74 Em formação", "75-89 Confirmada", "90-100 Alta qualidade"])
    trades = trades.assign(faixa_score=faixas.astype(str))
    datas = np.sort(trades["data"].unique())
    corte = datas[int(len(datas) * 0.6)] if len(datas) >= 5 else datas[-1]
    trades = trades.assign(amostra_periodo=np.where(trades["data"] < corte,
                                                    "calibração (60% iniciais)", "validação (40% finais)"))
    md = ["# Backtest — Bascka Reversal V2\n",
          f"Operações: **{len(trades)}** · ativos: **{trades['ticker'].nunique()}** · "
          f"período: {trades['data'].min()} a {trades['data'].max()} · custo: {CUSTO}% ida e volta\n",
          "> Resultado histórico não garante resultado futuro. Operações de ativos diferentes se sobrepõem no tempo, "
          "então o drawdown abaixo é uma aproximação. Grupos com menos de 30 operações são pouco confiáveis.\n"]

    geral = []
    for k in ALVOS:
        m = metricas(trades.sort_values("data"), k)
        if m["n"]:
            geral.append({"Alvo": f"{k}R", "Operações": m["n"], "Acerto %": round(m["acerto"], 1),
                          "R médio (expectativa)": round(m["R_medio"], 2),
                          "Profit Factor": "∞" if np.isinf(m["PF"]) else round(m["PF"], 2),
                          "Drawdown máx. (R)": round(m["DD_R"], 1),
                          "Falsos sinais %": round(m["falsos"], 1)})
    md += ["## Geral (todas as modalidades)\n", to_md(pd.DataFrame(geral))]
    md += ["## Por modalidade de entrada\n", to_md(tabela_grupos(trades, "modo", ["Antecipada", "Confirmada", "Reteste"]))]
    md += ["## Por faixa de score\n", to_md(tabela_grupos(
        trades, "faixa_score", ["40-59 Observação", "60-74 Em formação", "75-89 Confirmada", "90-100 Alta qualidade"]))]
    md += ["## Por direção\n", to_md(tabela_grupos(trades, "direcao"))]
    md += ["## Por alinhamento com o semanal\n", to_md(tabela_grupos(trades, "alinhamento", ["Alinhado", "Neutro", "Contra"]))]
    md += ["## Por regime de mercado (IBOV)\n", to_md(tabela_grupos(trades, "regime"))]
    md += ["## Calibração × validação (fora da amostra)\n", to_md(tabela_grupos(trades, "amostra_periodo"))]
    md += ["## Antecedência\n",
           "`captura mediana %` = quanto do movimento (do fundo/topo até o extremo dos 20 pregões seguintes) "
           "ainda estava pela frente na entrada. Quanto maior, mais cedo o sinal pegou a virada.\n"]
    return "\n".join(md), trades


# ==================== EXECUÇÃO ====================
def baixar_e_preparar(ticker, left, right):
    d = sc.baixar_historico(ticker, period=PERIODO)
    if d is None or d.empty or len(d) < WARMUP + 60:
        return ticker, None
    return ticker, sc.preparar_indicadores(d, left, right)


def main():
    t0 = time.time()
    deadline = t0 + MAX_MIN * 60
    p = {**V2_DEFAULT}
    struct = {**sc.STRUCT_DEFAULT}
    ranking = sc.rank_by_liquidity(UNIVERSO, top_n=TOP_N, min_vol=MIN_VOL)
    if not ranking:
        print("Sem ranking de liquidez (falha de download).")
        sys.exit(1)
    alvo = [t for t, _ in ranking]
    ibov = sc.baixar_ibov(PERIODO)
    print(f"Ativos: {len(alvo)} | IBOV: {'ok' if ibov is not None else 'indisponível'} | período: {PERIODO}")

    with ThreadPoolExecutor(max_workers=4) as ex:
        dados = {t: d for t, d in ex.map(lambda t: baixar_e_preparar(t, p["left"], p["right"]), alvo) if d is not None}
    print(f"Baixados e preparados: {len(dados)} ativos ({time.time() - t0:.0f}s)")

    trades = []
    args = [(t, d, ibov, struct, p, WARMUP, deadline, CUSTO) for t, d in dados.items()]
    if WORKERS > 1:
        with ProcessPoolExecutor(max_workers=WORKERS) as ex:
            for tk, tr in ex.map(bt_ticker, *zip(*args)):
                trades.extend(tr)
                print(f"  {tk}: {len(tr)} operações")
    else:
        for a in args:
            tk, tr = bt_ticker(*a)
            trades.extend(tr)
            print(f"  {tk}: {len(tr)} operações")

    parcial = time.time() > deadline
    if not trades:
        print("Nenhuma operação gerada no período.")
        return
    df = pd.DataFrame(trades)
    md, df = relatorio(df)
    if parcial:
        md = "> ⚠️ Tempo máximo atingido: resultado PARCIAL.\n\n" + md
    os.makedirs(OUT, exist_ok=True)
    df.drop(columns=["faixa_score"], errors="ignore").to_csv(os.path.join(OUT, "backtest_resultados.csv"), index=False)
    with open(os.path.join(OUT, "backtest_resumo.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(md)

    if os.environ.get("BT_TELEGRAM", "1") == "1":
        linhas = ["<b>📊 Backtest Bascka Reversal V2</b>",
                  f"{len(df)} operações · {df['ticker'].nunique()} ativos · {df['data'].min()} a {df['data'].max()}", ""]
        for modo in ("Antecipada", "Confirmada", "Reteste"):
            g = df[df["modo"] == modo].sort_values("data")
            m = metricas(g, 2.0) if len(g) else {"n": 0}
            if m["n"]:
                pf = "∞" if np.isinf(m["PF"]) else f"{m['PF']:.2f}"
                linhas.append(f"{modo} (alvo 2R): {m['n']} op · acerto {m['acerto']:.0f}% · "
                              f"R médio {m['R_medio']:.2f} · PF {pf}" + (" ⚠️ amostra pequena" if m["n"] < 30 else ""))
        linhas.append("\nDetalhes completos na página do run no GitHub (Summary) e no artefato.")
        sc.send_telegram("\n".join(linhas), os.environ.get("TELEGRAM_TOKEN", ""),
                         os.environ.get("TELEGRAM_CHAT_ID", ""), verbose=True)
    print(f"Concluído em {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
