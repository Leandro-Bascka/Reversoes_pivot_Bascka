"""Lógica do B3 Pivot Scanner (sem dependência de Streamlit).
Usada pelo app (app.py) e pelo job automático de alertas (alert_job.py)."""
import time
import yfinance as yf
from reversal_v2 import (adicionar_indicadores_v2, alinhar_mercado, avaliar, passa_filtro,
                         tendencia_semanal, V2_DEFAULT)
import pandas as pd
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ==================== LISTA DE ATIVOS ====================
TICKERS = [
    "PETR4.SA", "PETR3.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA", "BBAS3.SA",
    "B3SA3.SA", "WEGE3.SA", "ABEV3.SA", "ITSA4.SA", "RENT3.SA", "EQTL3.SA",
    "PRIO3.SA", "SUZB3.SA", "RADL3.SA", "LREN3.SA", "BBSE3.SA", "GGBR4.SA",
    "RAIL3.SA", "VIVT3.SA", "CSAN3.SA", "ENEV3.SA", "CMIG4.SA", "TOTS3.SA",
    "HAPV3.SA", "EMBJ3.SA", "CSNA3.SA", "UGPA3.SA", "MBRF3.SA",
    "KLBN11.SA", "SANB11.SA", "BPAC11.SA", "MULT3.SA", "CYRE3.SA", "ENGI11.SA",
    "CPLE3.SA", "SBSP3.SA", "MOTV3.SA", "TIMS3.SA", "FLRY3.SA",
    "HYPE3.SA", "MGLU3.SA", "ASAI3.SA", "AXIA3.SA", "VBBR3.SA", "RDOR3.SA",
    "CSMG3.SA", "ALOS3.SA", "DIRR3.SA", "CURY3.SA", "PSSA3.SA", "BRAP4.SA",
    "USIM5.SA", "CMIN3.SA", "GOAU4.SA", "MRVE3.SA", "EZTC3.SA", "IGTI11.SA"
]

# ==================== PARÂMETROS DA ESTRUTURA ====================
STRUCT_DEFAULT = {
    "n_pivots": 2,            # nº de fundos (topos) descendentes (ascendentes) que caracterizam a tendência anterior
    "tol": 0.003,             # 0,3%: abaixo disso, fundos/topos são tratados como "iguais" (duplo fundo/topo)
    "min_move_atr": 1.5,      # tamanho mínimo do movimento anterior, em múltiplos de ATR
    "exigir_topos": True,     # exigir também topos descendentes (fundos ascendentes) na tendência anterior
    "exigir_estrutura": True, # só listar sinais com etapa 1, 2 ou 3
}

ESTAGIOS = {0: "—", 1: "1·Aviso", 2: "2·Virada", 3: "3·Confirmada"}
PTS_ETAPA = {0: 0, 1: 1, 2: 2, 3: 4}


# ==================== TELEGRAM ====================
def send_telegram(message: str, token: str, chat_id: str, verbose: bool = False) -> bool:
    """Envia mensagem ao Telegram. Com verbose=True imprime o motivo da falha
    (a resposta do Telegram nunca contém o token)."""
    # Limpa espaços, quebras de linha e aspas coladas por engano junto com o segredo.
    token = (token or "").strip().strip("\"'")
    chat_id = str(chat_id or "").strip().strip("\"'")
    if not token or not chat_id:
        if verbose:
            print("Telegram: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID está vazio "
                  "(confira o nome e o tipo do segredo no GitHub).")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(
            url,
            data={"chat_id": chat_id, "text": message[:4000], "parse_mode": "HTML"},
            timeout=10,
        )
        if not r.ok and verbose:
            print(f"Telegram respondeu {r.status_code}: {r.text}")
        return r.ok
    except Exception as e:
        if verbose:
            print(f"Telegram: erro de conexão ({type(e).__name__})")
        return False


def build_alert_message(rows, titulo="B3 Pivot Scanner - Alertas"):
    """rows: lista de dicts de resultados."""
    msg = f"<b>🎯 {titulo}</b>\n{datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    for r in rows:
        msg += f"{r['Alerta']}\n"
        msg += f"<b>{r['Ticker']}</b> | Score: {r['Score']} | Liquidez: #{r['Liq Rank']}\n"
        msg += f"Estágio: {r.get('Estágio', '—')}"
        if r.get("Perna ATR") is not None and r.get("Perna ATR") == r.get("Perna ATR"):
            msg += f" | Mov. anterior: {r['Perna ATR']}x ATR"
        msg += "\n"
        msg += f"Pivô: R$ {r['Preço Pivô']} → Atual: R$ {r['Preço Atual']}\n"
        nivel = r.get("Nível")
        if nivel is not None and nivel == nivel:
            msg += f"Nível de confirmação: R$ {nivel}\n"
        msg += f"Vol Rel: {r['Vol Rel']}x | RSI: {r['RSI']} | Div: {r['Divergência']}\n\n"
    return msg


# ==================== FUNÇÕES TÉCNICAS (originais) ====================
def detect_pivots(df, left=5, right=3):
    df = df.copy()
    high = df["High"].values
    low = df["Low"].values
    n = len(df)
    ph = np.zeros(n, dtype=bool)
    pl = np.zeros(n, dtype=bool)

    for i in range(left, n - right):
        if high[i] == max(high[i-left:i+right+1]):
            ph[i] = True
        if low[i] == min(low[i-left:i+right+1]):
            pl[i] = True

    df["PH"] = ph
    df["PL"] = pl
    return df


def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_atr(df, period=14):
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def find_divergences(df, lookback=35):
    recent = df.tail(lookback + 10).copy()
    ph_idx = recent[recent["PH"]].index.tolist()
    pl_idx = recent[recent["PL"]].index.tolist()

    bull_div = False
    bear_div = False

    if len(pl_idx) >= 2:
        last, prev = pl_idx[-1], pl_idx[-2]
        if (df.loc[last, "Low"] < df.loc[prev, "Low"] and
            df.loc[last, "RSI"] > df.loc[prev, "RSI"]):
            bull_div = True

    if len(ph_idx) >= 2:
        last, prev = ph_idx[-1], ph_idx[-2]
        if (df.loc[last, "High"] > df.loc[prev, "High"] and
            df.loc[last, "RSI"] < df.loc[prev, "RSI"]):
            bear_div = True

    return bull_div, bear_div


# ==================== ESTRUTURA DE MERCADO (novo) ====================
def analyze_structure(df, direction="up", n_pivots=2, tol=0.003,
                      min_move_atr=1.5, exigir_topos=True, divergence=False):
    """Classifica o início de uma reversão pela sequência de fundos/topos.

    direction="up"   -> reversão de ALTA  (tendência anterior de baixa)
    direction="down" -> reversão de BAIXA (tendência anterior de alta)

    Etapas (exemplo de alta; a de baixa é o espelho):
      1 Aviso:     último fundo é mais baixo que o anterior (n fundos descendentes,
                   topos descendentes) COM divergência no RSI. A virada ainda não começou.
      2 Virada:    surge um fundo ASCENDENTE depois da sequência de fundos descendentes.
      3 Confirmada: o preço fecha acima do topo da recuperação (quebra de estrutura).

    Exige que o movimento anterior tenha tamanho mínimo (min_move_atr x ATR).
    Retorna dict: etapa (0-3), nivel (preço de confirmação), barras (barras desde o
    evento da etapa), perna_atr (tamanho do movimento anterior em ATR).
    """
    res = {"etapa": 0, "nivel": None, "barras": None, "perna_atr": None}

    # Para reversão de baixa, espelhamos os preços (assim a mesma lógica serve).
    if direction == "up":
        lo, hi, cl = df["Low"].values, df["High"].values, df["Close"].values
        pl = np.where(df["PL"].values)[0]
        ph = np.where(df["PH"].values)[0]
    else:
        lo, hi, cl = -df["High"].values, -df["Low"].values, -df["Close"].values
        pl = np.where(df["PH"].values)[0]
        ph = np.where(df["PL"].values)[0]

    atr = df["ATR"].values
    n = len(df)

    # Consolida pivôs: dois fundos seguidos sem um topo no meio (ou empates em candles
    # vizinhos) viram um só, ficando o mais extremo. Assim fundos e topos se alternam.
    eventos = sorted([(int(p), "L") for p in pl] + [(int(p), "H") for p in ph])
    swings = []
    for p, t in eventos:
        if swings and swings[-1][1] == t:
            q = swings[-1][0]
            if (t == "L" and lo[p] < lo[q]) or (t == "H" and hi[p] > hi[q]):
                swings[-1] = (p, t)
        else:
            swings.append((p, t))
    pl = np.array([p for p, t in swings if t == "L"], dtype=int)
    ph = np.array([p for p, t in swings if t == "H"], dtype=int)

    def lower(a, b):   # a é "mais baixo" que b, acima da tolerância
        return (b - a) > tol * abs(b)

    def higher(a, b):
        return (a - b) > tol * abs(b)

    def tendencia_anterior_ok(ref):
        """ref = barra do fundo mais baixo (LL) da tendência anterior."""
        ini = max(0, ref - 40)
        perna = hi[ini:ref + 1].max() - lo[ref]
        a = atr[ref]
        if not (a > 0):
            return False, None
        perna_atr = perna / a
        if perna_atr < min_move_atr:
            return False, round(float(perna_atr), 1)
        if exigir_topos:
            antes = ph[ph < ref]
            if len(antes) < 2 or not lower(hi[antes[-1]], hi[antes[-2]]):
                return False, round(float(perna_atr), 1)
        return True, round(float(perna_atr), 1)

    # ---------- Etapas 2 e 3: fundo ascendente depois de fundos descendentes ----------
    if len(pl) >= n_pivots + 1:
        seq = pl[-(n_pivots + 1):]          # [Ln, ..., L1, L0] em ordem cronológica
        l0, l1 = seq[-1], seq[-2]
        descendentes = all(lower(lo[seq[k + 1]], lo[seq[k]]) for k in range(len(seq) - 2))
        invalido = n > l0 + 1 and lo[l0 + 1:].min() < lo[l0]   # perdeu o fundo ascendente

        if descendentes and higher(lo[l0], lo[l1]) and not invalido:
            ok, perna = tendencia_anterior_ok(l1)
            if ok:
                nivel = hi[l1:l0 + 1].max()   # topo da recuperação entre o LL e o fundo ascendente
                apos = np.where(cl[l0 + 1:] > nivel)[0]
                if len(apos) and cl[-1] > nivel:
                    j = l0 + 1 + apos[0]
                    etapa, barras = 3, n - 1 - j
                else:
                    etapa, barras = 2, n - 1 - l0
                nivel_real = float(nivel) if direction == "up" else float(-nivel)
                return {"etapa": etapa, "nivel": round(nivel_real, 2),
                        "barras": int(barras), "perna_atr": perna,
                        "l0": int(l0), "l1": int(l1)}

    # ---------- Etapa 1: novo fundo mais baixo com divergência ----------
    if divergence and len(pl) >= n_pivots:
        seq = pl[-n_pivots:]
        l0 = seq[-1]
        descendentes = all(lower(lo[seq[k + 1]], lo[seq[k]]) for k in range(len(seq) - 1))
        invalido = n > l0 + 1 and lo[l0 + 1:].min() < lo[l0]
        if descendentes and not invalido:
            ok, perna = tendencia_anterior_ok(l0)
            if ok:
                return {"etapa": 1, "nivel": None, "barras": int(n - 1 - l0), "perna_atr": perna,
                        "l0": int(l0), "l1": int(seq[-2])}

    return res


def definir_alerta(score, vol_rel, etapa, div, min_score, labels):
    """Sem estrutura (etapa 0): regras originais. Com estrutura: a etapa limita o alerta
    (etapa 1 = só observação, etapa 2 = até COMPRA/VENDA, etapa 3 = pode ser FORTE)."""
    forte, normal, obs = labels
    if etapa == 0:
        if score >= 8 and div and vol_rel >= 1.8:
            return forte
        if score >= 7:
            return normal
    else:
        if etapa == 3 and score >= 8 and vol_rel >= 1.8:
            return forte
        if etapa >= 2 and score >= 7:
            return normal
    if score >= min_score:
        return obs
    return None


# ==================== LIQUIDEZ ====================
def rank_by_liquidity(tickers, top_n=30, min_vol=0.0):
    """Baixa os últimos 3 meses de todos os tickers de uma vez, calcula o
    volume financeiro médio (20 pregões) e devolve os top_n mais líquidos
    como [(ticker, volume_financeiro_medio), ...] em ordem decrescente."""
    try:
        data = yf.download(
            tickers, period="3mo", progress=False, auto_adjust=True,
            group_by="ticker", threads=True, timeout=30,
        )
    except Exception:
        data = None

    def liquidez(d):
        if isinstance(d.columns, pd.MultiIndex):
            d = d.copy()
            d.columns = d.columns.get_level_values(0)
        d = d.dropna()
        return float((d["Volume"] * d["Close"]).tail(20).mean())

    rows = []
    for t in tickers:
        try:
            vf = liquidez(data[t])
        except Exception:
            vf = None
        # Se o ativo falhou no download em lote (ex.: 'database is locked'), tenta de novo
        # sozinho, para uma ação líquida não sumir do ranking sem aviso.
        if vf is None or vf != vf:
            try:
                vf = liquidez(baixar_historico(t, period="3mo"))
            except Exception:
                vf = None
        if vf is not None and vf == vf and vf >= min_vol:
            rows.append((t, vf))

    rows.sort(key=lambda x: -x[1])
    return rows[:top_n]


# ==================== ANÁLISE POR ATIVO ====================
def baixar_historico(ticker, tentativas=3, period="2y"):
    """Baixa 1 ano de candles. O yfinance usa um cache em SQLite que às vezes dá
    'database is locked' quando vários downloads rodam em paralelo; nesse caso ele
    devolve vazio, então tentamos de novo com uma pequena pausa."""
    df = pd.DataFrame()
    for i in range(tentativas):
        try:
            df = yf.download(ticker, period=period, progress=False, auto_adjust=True, timeout=15)
        except Exception:
            df = pd.DataFrame()
        if not df.empty:
            return df
        time.sleep(0.7 * (i + 1))
    return df


def process_ticker(ticker, left, right, min_vol, min_score, struct=None, coletor=None):
    """Lógica original (pivôs + estrutura). Se 'coletor' (dict) for passado, devolve nele o
    DataFrame já com todos os indicadores, para a camada V2 reaproveitar sem baixar de novo."""
    struct = {**STRUCT_DEFAULT, **(struct or {})}
    skw = dict(n_pivots=struct["n_pivots"], tol=struct["tol"],
               min_move_atr=struct["min_move_atr"], exigir_topos=struct["exigir_topos"])
    try:
        df = baixar_historico(ticker)
        if df.empty or len(df) < 80:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        vol_fin = (df["Volume"] * df["Close"]).tail(20).mean()
        if vol_fin < min_vol:
            return None

        df = detect_pivots(df, left=left, right=right)
        df["RSI"] = calculate_rsi(df["Close"])
        df["ATR"] = calculate_atr(df)
        df["EMA20"] = df["Close"].ewm(span=20).mean()
        df["EMA50"] = df["Close"].ewm(span=50).mean()
        df["Vol_MA"] = df["Volume"].rolling(20).mean()
        adicionar_indicadores_v2(df)          # colunas extras da V2 (não afetam a lógica original)
        if coletor is not None:
            coletor["df"] = df
            coletor["vol_fin"] = float(vol_fin)

        last_ph = df[df["PH"]].tail(1)
        last_pl = df[df["PL"]].tail(1)
        results = []

        # --- Pivot Low (reversão de ALTA) ---
        if not last_pl.empty:
            idx = last_pl.index[0]
            days_ago = (df.index[-1] - idx).days
            barras_pivo = len(df) - 1 - df.index.get_loc(idx)
            if days_ago <= 40:
                price = float(df.loc[idx, "Low"])
                vol_rel = float(df.loc[idx, "Volume"] / df.loc[idx, "Vol_MA"]) if df.loc[idx, "Vol_MA"] > 0 else 1
                rsi = float(df.loc[idx, "RSI"])
                current = float(df["Close"].iloc[-1])
                bull_div, _ = find_divergences(df)
                est = analyze_structure(df, "up", divergence=bull_div, **skw)

                score = 2
                if vol_rel >= 1.5: score += 2
                if vol_rel >= 2.5: score += 1
                if rsi < 35: score += 1
                if bull_div: score += 3
                if current > df["EMA20"].iloc[-1]: score += 1
                if current > df["EMA50"].iloc[-1]: score += 1

                candle = df.loc[idx]
                body = abs(candle["Close"] - candle["Open"])
                lower_wick = min(candle["Open"], candle["Close"]) - candle["Low"]
                if lower_wick > body * 1.5:
                    score += 1

                score += PTS_ETAPA[est["etapa"]]

                alerta = definir_alerta(
                    score, vol_rel, est["etapa"], bull_div, min_score,
                    ("🔥 FORTE COMPRA", "🟢 COMPRA", "🟡 Observação Compra"))

                if alerta and score >= min_score and (est["etapa"] > 0 or not struct["exigir_estrutura"]):
                    results.append({
                        "Ticker": ticker.replace(".SA", ""),
                        "Tipo": "Pivot Low",
                        "Alerta": alerta,
                        "Estágio": ESTAGIOS[est["etapa"]],
                        "Etapa": est["etapa"],
                        "Preço Pivô": round(price, 2),
                        "Preço Atual": round(current, 2),
                        "Nível": est["nivel"],
                        "Perna ATR": est["perna_atr"],
                        "Dias": days_ago,
                        "BarrasPivo": barras_pivo,
                        "Barras": est["barras"] if est["etapa"] > 0 else barras_pivo,
                        "Vol Rel": round(vol_rel, 2),
                        "RSI": round(rsi, 1),
                        "Divergência": "Sim" if bull_div else "Não",
                        "Score": score,
                        "Volume Médio": round(vol_fin),
                        "_df": df,
                        "_tipo": "low",
                        "_idx": idx
                    })

        # --- Pivot High (reversão de BAIXA) ---
        if not last_ph.empty:
            idx = last_ph.index[0]
            days_ago = (df.index[-1] - idx).days
            barras_pivo = len(df) - 1 - df.index.get_loc(idx)
            if days_ago <= 40:
                price = float(df.loc[idx, "High"])
                vol_rel = float(df.loc[idx, "Volume"] / df.loc[idx, "Vol_MA"]) if df.loc[idx, "Vol_MA"] > 0 else 1
                rsi = float(df.loc[idx, "RSI"])
                current = float(df["Close"].iloc[-1])
                _, bear_div = find_divergences(df)
                est = analyze_structure(df, "down", divergence=bear_div, **skw)

                score = 2
                if vol_rel >= 1.5: score += 2
                if vol_rel >= 2.5: score += 1
                if rsi > 65: score += 1
                if bear_div: score += 3
                if current < df["EMA20"].iloc[-1]: score += 1
                if current < df["EMA50"].iloc[-1]: score += 1

                candle = df.loc[idx]
                body = abs(candle["Close"] - candle["Open"])
                upper_wick = candle["High"] - max(candle["Open"], candle["Close"])
                if upper_wick > body * 1.5:
                    score += 1

                score += PTS_ETAPA[est["etapa"]]

                alerta = definir_alerta(
                    score, vol_rel, est["etapa"], bear_div, min_score,
                    ("🔥 FORTE VENDA", "🔴 VENDA", "🟠 Observação Venda"))

                if alerta and score >= min_score and (est["etapa"] > 0 or not struct["exigir_estrutura"]):
                    results.append({
                        "Ticker": ticker.replace(".SA", ""),
                        "Tipo": "Pivot High",
                        "Alerta": alerta,
                        "Estágio": ESTAGIOS[est["etapa"]],
                        "Etapa": est["etapa"],
                        "Preço Pivô": round(price, 2),
                        "Preço Atual": round(current, 2),
                        "Nível": est["nivel"],
                        "Perna ATR": est["perna_atr"],
                        "Dias": days_ago,
                        "BarrasPivo": barras_pivo,
                        "Barras": est["barras"] if est["etapa"] > 0 else barras_pivo,
                        "Vol Rel": round(vol_rel, 2),
                        "RSI": round(rsi, 1),
                        "Divergência": "Sim" if bear_div else "Não",
                        "Score": score,
                        "Volume Médio": round(vol_fin),
                        "_df": df,
                        "_tipo": "high",
                        "_idx": idx
                    })

        return results if results else None

    except Exception:
        return None


# ==================== VARREDURA COMPLETA ====================
ORDEM_ALERTA = {
    "🔥 FORTE COMPRA": 0, "🔥 FORTE VENDA": 1, "🟢 COMPRA": 2, "🔴 VENDA": 3,
    "🟡 Observação Compra": 4, "🟠 Observação Venda": 5,
}


def run_scan(left=5, right=3, min_vol=8_000_000, min_score=6, top_n=30,
             tickers=None, workers=5, progress_cb=None, struct=None):
    """1) ranqueia por liquidez e fica só com os top_n mais líquidos;
    2) roda a análise de pivôs + estrutura nesses ativos.
    Retorna (DataFrame ordenado por força do alerta e score ou None, ranking)."""
    tickers = tickers or TICKERS
    ranking = rank_by_liquidity(tickers, top_n=top_n, min_vol=min_vol)
    if not ranking:
        return None, []

    liq_rank = {t.replace(".SA", ""): i + 1 for i, (t, _) in enumerate(ranking)}
    alvo = [t for t, _ in ranking]

    all_results = []
    total = len(alvo)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(process_ticker, t, left, right, min_vol, min_score, struct): t for t in alvo}
        for i, fut in enumerate(as_completed(futures)):
            res = fut.result()
            if res:
                all_results.extend(res)
            if progress_cb:
                progress_cb(i + 1, total, len(all_results))

    if not all_results:
        return None, ranking

    for r in all_results:
        r["Liq Rank"] = liq_rank.get(r["Ticker"], 999)

    df = pd.DataFrame(all_results)
    df["ordem"] = df["Alerta"].map(ORDEM_ALERTA)
    df = df.sort_values(["ordem", "Score", "Liq Rank"], ascending=[True, False, True]).reset_index(drop=True)
    return df, ranking


# ==================== CAMADA V2 (Bascka Reversal) ====================
def avaliar_em(df, t, direction, struct=None, p=None, mercado=None):
    """Avalia a reversão como ela seria vista no fechamento da barra t (sem olhar o futuro).
    Os pivôs só valem depois de 'right' barras, então os mais recentes são mascarados."""
    struct = {**STRUCT_DEFAULT, **(struct or {})}
    p = {**V2_DEFAULT, **(p or {})}
    d = df.iloc[:t + 1].copy()
    ok = np.arange(t + 1) <= (t - p["right"])
    d["PL"] = d["PL"].values & ok
    d["PH"] = d["PH"].values & ok
    bull, bear = find_divergences(d)
    est = analyze_structure(d, direction, divergence=(bull if direction == "up" else bear),
                            n_pivots=struct["n_pivots"], tol=struct["tol"],
                            min_move_atr=struct["min_move_atr"], exigir_topos=struct["exigir_topos"])
    return avaliar(d, direction, est, p, mercado, tendencia_semanal(d))


def baixar_ibov(period="2y"):
    try:
        d = baixar_historico("^BVSP", period=period)
        if d is None or d.empty:
            return None
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        return d[["Close"]]
    except Exception:
        return None


def _linha_v2(ticker, df, vol_fin, res):
    al = res["alvos"]
    return {
        "Ticker": ticker.replace(".SA", ""),
        "Direção": res["direcao"],
        "Classe": res["classe"],
        "Score V2": res["score"],
        "Modo": res["modo"],
        "Modos": " + ".join(res["modos"]) if res["modos"] else "—",
        "Etapa": res["etapa"],
        "Estágio": ESTAGIOS[res["etapa"]],
        "Semanal": f"{res['semanal']} ({res['alinhamento']})",
        "Entrada": res["entrada"], "Stop": res["stop"],
        "Alvo 1": al[0], "Alvo 2": al[1], "Alvo 3": al[2],
        "Stop %": res["risco_pct"], "R/R estrutural": res["rr_estrutural"],
        "Vol Rel": res["vol_rel"], "Nível": res["nivel"],
        "Data pivô": res["data_pivo"].strftime("%Y-%m-%d"),
        "Confirmado em": res["data_confirmacao"].strftime("%Y-%m-%d"),
        "Sinal desde": res["sinal_desde"].strftime("%Y-%m-%d"),
        "Novo": bool(res.get("novo")),
        "Evidências": "; ".join(res["evidencias"]),
        "Grupos": res["grupos"],
        "Volume Médio": round(vol_fin),
        "_df": df,
        "_tipo": "low" if res["direcao"] == "Compra" else "high",
        "_res": res,
    }


def analisar_v2(ticker, df, vol_fin, left, right, struct, p, ibov, perfil, tipo):
    mercado = alinhar_mercado(ibov, df.index)
    t = len(df) - 1
    rows = []
    for direction in ("up", "down"):
        res = avaliar_em(df, t, direction, struct, p, mercado)
        if res is None:
            continue
        ontem = avaliar_em(df, t - 1, direction, struct, p, mercado)
        novos = [m for m in res["modos"] if not (ontem and m in ontem["modos"])]
        res["novo"] = bool(novos)
        res["modos_novos"] = novos
        if passa_filtro(res, perfil, tipo):
            rows.append(_linha_v2(ticker, df, vol_fin, res))
    return rows


def process_ticker_full(ticker, left, right, min_vol, min_score, struct, p, ibov,
                        perfil="Equilibrado", tipo="dois", usar_v2=True):
    """Uma única baixada por ativo: devolve (linhas_v1, linhas_v2, df)."""
    col = {}
    v1 = process_ticker(ticker, left, right, min_vol, min_score, struct, coletor=col)
    v2 = []
    if usar_v2 and "df" in col:
        try:
            v2 = analisar_v2(ticker, col["df"], col["vol_fin"], left, right, struct, p, ibov, perfil, tipo)
        except Exception as e:
            print(f"V2 falhou em {ticker}: {type(e).__name__}: {e}")
    return v1, v2, col.get("df")


def run_scan_full(left=5, right=3, min_vol=8_000_000, min_score=6, top_n=30, tickers=None,
                  workers=5, progress_cb=None, struct=None, perfil="Equilibrado",
                  tipo="dois", usar_v2=True):
    """Varredura completa: lógica original + camada V2 numa única passada.
    Retorna dict: v1 (DataFrame|None), v2 (DataFrame|None), ranking, dfs {ticker: DataFrame}."""
    struct = {**STRUCT_DEFAULT, **(struct or {})}
    tickers = tickers or TICKERS
    ranking = rank_by_liquidity(tickers, top_n=top_n, min_vol=min_vol)
    out = {"v1": None, "v2": None, "ranking": ranking, "dfs": {}}
    if not ranking:
        return out

    p = {**V2_DEFAULT, "left": left, "right": right, "min_move_atr": struct["min_move_atr"]}
    ibov = baixar_ibov() if usar_v2 else None
    out["ibov_ok"] = ibov is not None
    liq_rank = {t.replace(".SA", ""): i + 1 for i, (t, _) in enumerate(ranking)}
    alvo = [t for t, _ in ranking]

    r1, r2 = [], []
    total = len(alvo)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_ticker_full, t, left, right, min_vol, min_score, struct, p,
                          ibov, perfil, tipo, usar_v2): t for t in alvo}
        for i, fut in enumerate(as_completed(futs)):
            v1, v2, d = fut.result()
            if v1:
                r1.extend(v1)
            if v2:
                r2.extend(v2)
            if d is not None:
                out["dfs"][futs[fut]] = d
            if progress_cb:
                progress_cb(i + 1, total, len(r1) + len(r2))

    for r in r1 + r2:
        r["Liq Rank"] = liq_rank.get(r["Ticker"], 999)
    if r1:
        d1 = pd.DataFrame(r1)
        d1["ordem"] = d1["Alerta"].map(ORDEM_ALERTA)
        out["v1"] = d1.sort_values(["ordem", "Score", "Liq Rank"],
                                   ascending=[True, False, True]).reset_index(drop=True)
    if r2:
        out["v2"] = pd.DataFrame(r2).sort_values(["Score V2", "Liq Rank"],
                                                 ascending=[False, True]).reset_index(drop=True)
    return out


def build_alert_message_v2(rows, titulo="Bascka Reversal V2"):
    import html
    msg = f"<b>🎯 {titulo}</b>\n{datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    for r in rows:
        seta = "🟢" if r["Direção"] == "Compra" else "🔴"
        msg += f"{seta} <b>{r['Ticker']}</b> · {r['Direção']} · {r['Modo']}\n"
        msg += f"{r['Classe']} | Score {r['Score V2']}/100 | Liquidez #{r['Liq Rank']}\n"
        msg += (f"Entrada R$ {r['Entrada']} | Stop R$ {r['Stop']} ({r['Stop %']}%)\n"
                f"Alvos: R$ {r['Alvo 1']} (1,5R) · {r['Alvo 2']} (2R) · {r['Alvo 3']} (3R)\n")
        msg += f"Semanal: {r['Semanal']} | R/R até o topo: {r['R/R estrutural']}\n"
        evid = [e for e in r["Evidências"].split("; ") if e][:4]
        if evid:
            msg += "• " + html.escape("\n• ".join(evid)) + "\n"
        msg += "\n"
    return msg


def preparar_indicadores(df, left=5, right=3):
    """Mesmos indicadores que o scanner calcula por ativo (usado pelo backtest)."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = detect_pivots(df.copy(), left=left, right=right)
    df["RSI"] = calculate_rsi(df["Close"])
    df["ATR"] = calculate_atr(df)
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["Vol_MA"] = df["Volume"].rolling(20).mean()
    return adicionar_indicadores_v2(df)
