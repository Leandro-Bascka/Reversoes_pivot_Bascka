"""Histórico de sinais e resultados (CSV) e resolução de operações em múltiplos de R.

Regras de execução (as mesmas no histórico ao vivo e no backtest):
  - o sinal nasce no FECHAMENTO da barra t; a entrada é a ABERTURA da barra seguinte;
  - o stop é o do sinal; o risco R = |entrada - stop|; alvos em 1,5R, 2R e 3R;
  - se, na mesma barra, o stop e o alvo forem tocados, vale o STOP (hipótese conservadora);
  - gap além do stop sai na abertura (pior que -1R); gap além do alvo conta só o alvo;
  - sem toque em 20 barras, sai no fechamento da 20ª barra;
  - custo (corretagem + emolumentos + derrapagem) descontado em R.
Cada alvo é avaliado separadamente (corrida entre o stop e aquele alvo).
"""
import os
import numpy as np
import pandas as pd

ALVOS_R = (1.5, 2.0, 3.0)
MAX_BARRAS = 20
CUSTO_PCT = 0.15     # % do preço, ida e volta

COLUNAS = ["id", "ticker", "direcao", "modo", "classe", "score", "data_sinal", "entrada", "stop",
           "alvo1", "alvo2", "alvo3", "risco_pct", "status", "data_resultado",
           "r_alvo1", "r_alvo2", "r_alvo3"]


def resolver(o, h, l, c, direcao, stop, alvos_r=ALVOS_R, custo_pct=CUSTO_PCT, max_barras=MAX_BARRAS):
    """o, h, l, c: arrays das barras APÓS o sinal (a primeira é a de execução).
    Retorna None se o sinal for inválido (a abertura já passou do stop) ou não houver barras.
    Senão: {"entrada", "risco", "alvos": {k: {"r", "motivo", "barras"}}}."""
    if len(o) == 0:
        return None
    s = 1.0 if direcao == "Compra" else -1.0
    entrada = float(o[0])
    risco = s * (entrada - stop)
    if not risco > 0:
        return None
    custo_r = custo_pct / 100 * abs(entrada) / risco
    n = min(len(o), max_barras)
    out = {"entrada": entrada, "risco": float(risco), "alvos": {}}
    for k in alvos_r:
        alvo = entrada + s * k * risco
        r, motivo, barras = np.nan, "aberto", n
        for i in range(n):
            if s * (o[i] - stop) <= 0:                       # gap além do stop
                r, motivo, barras = s * (o[i] - entrada) / risco, "stop", i + 1
                break
            if s * (o[i] - alvo) >= 0:                       # gap além do alvo
                r, motivo, barras = k, "alvo", i + 1
                break
            adverso = l[i] if s > 0 else h[i]
            favor = h[i] if s > 0 else l[i]
            if s * (adverso - stop) <= 0:                    # stop vence se os dois forem tocados
                r, motivo, barras = -1.0, "stop", i + 1
                break
            if s * (favor - alvo) >= 0:
                r, motivo, barras = k, "alvo", i + 1
                break
            if i == n - 1 and len(o) >= max_barras:          # tempo esgotado
                r, motivo, barras = s * (c[i] - entrada) / risco, "tempo", i + 1
        if motivo != "aberto":
            r -= custo_r
        out["alvos"][k] = {"r": float(r), "motivo": motivo, "barras": int(barras)}
    return out


# ==================== HISTÓRICO EM CSV ====================
def carregar(path):
    if path and os.path.exists(path):
        try:
            return pd.read_csv(path, dtype={"data_sinal": str, "data_resultado": str})
        except Exception:
            pass
    return pd.DataFrame(columns=COLUNAS)


def id_sinal(r):
    """Identificador do sinal NOVO de uma linha V2 (ou None se não houver modalidade nova).
    A data é o dia em que o sinal ficou disponível (último candle), não a do pivô."""
    res = r["_res"]
    if not res.get("modos_novos"):
        return None
    modo = next(m for m in ("Reteste", "Confirmada", "Antecipada") if m in res["modos_novos"])
    return f"{r['Ticker']}|{r['Direção']}|{modo}|{r['_df'].index[-1].strftime('%Y-%m-%d')}"


def ids_registrados(path):
    hist = carregar(path)
    return set(hist["id"]) if len(hist) else set()


def registrar(path, linhas_v2):
    """Acrescenta os sinais NOVOS (Novo=True e com modalidade) sem duplicar. Devolve o DataFrame."""
    hist = carregar(path)
    ja = set(hist["id"]) if len(hist) else set()
    novas = []
    for r in linhas_v2:
        sid = id_sinal(r)
        if sid is None:
            continue
        modo = sid.split("|")[2]
        data = sid.split("|")[3]
        if sid in ja:
            continue
        ja.add(sid)
        novas.append({
            "id": sid, "ticker": r["Ticker"], "direcao": r["Direção"], "modo": modo,
            "classe": r["Classe"], "score": r["Score V2"], "data_sinal": data,
            "entrada": r["Entrada"], "stop": r["Stop"], "alvo1": r["Alvo 1"], "alvo2": r["Alvo 2"],
            "alvo3": r["Alvo 3"], "risco_pct": r["Stop %"], "status": "aberto",
            "data_resultado": "", "r_alvo1": np.nan, "r_alvo2": np.nan, "r_alvo3": np.nan,
        })
    if novas:
        hist = pd.concat([hist, pd.DataFrame(novas)], ignore_index=True)
        _salvar(path, hist)
    return hist


def atualizar_resultados(path, dfs, custo_pct=CUSTO_PCT):
    """Resolve os sinais abertos com os candles posteriores. dfs: {ticker.SA: DataFrame}."""
    hist = carregar(path)
    if hist.empty:
        return hist
    mudou = False
    for i, row in hist[hist["status"] == "aberto"].iterrows():
        df = dfs.get(f"{row['ticker']}.SA")
        if df is None:
            continue
        apos = df[df.index > pd.Timestamp(row["data_sinal"])]
        res = resolver(apos["Open"].values, apos["High"].values, apos["Low"].values,
                       apos["Close"].values, row["direcao"], float(row["stop"]), custo_pct=custo_pct)
        if res is None:
            if len(apos) > 0:   # abriu além do stop: sinal inválido
                hist.loc[i, "status"] = "invalidado"
                hist.loc[i, "data_resultado"] = apos.index[0].strftime("%Y-%m-%d")
                mudou = True
            continue
        fechados = 0
        for n_, k in enumerate(ALVOS_R, 1):
            a = res["alvos"][k]
            if a["motivo"] != "aberto":
                hist.loc[i, f"r_alvo{n_}"] = round(a["r"], 3)
                fechados += 1
        if fechados == len(ALVOS_R):
            ult = max(a["barras"] for a in res["alvos"].values())
            hist.loc[i, "status"] = "encerrado"
            hist.loc[i, "data_resultado"] = apos.index[min(ult, len(apos)) - 1].strftime("%Y-%m-%d")
        mudou = mudou or fechados > 0
    if mudou:
        _salvar(path, hist)
    return hist


def resumo(hist):
    """Taxa de acerto e R médio por alvo, só dos sinais já encerrados."""
    enc = hist[hist["status"] == "encerrado"] if len(hist) else hist
    linhas = []
    for n_, k in enumerate(ALVOS_R, 1):
        r = pd.to_numeric(enc[f"r_alvo{n_}"], errors="coerce").dropna() if len(enc) else pd.Series(dtype=float)
        linhas.append({"Alvo": f"{k}R", "Sinais": int(len(r)),
                       "Taxa de acerto %": round(100 * (r > 0).mean(), 1) if len(r) else None,
                       "R médio": round(r.mean(), 2) if len(r) else None})
    return pd.DataFrame(linhas)


def _salvar(path, hist):
    if not path:
        return
    pasta = os.path.dirname(path)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    hist.to_csv(path, index=False)
