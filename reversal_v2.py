"""Bascka Reversal V2 — camada adicional que NÃO altera a lógica original.

Reaproveita os pivôs e a estrutura (analyze_structure) do scanner e acrescenta:
  - Liquidity Sweep, Order Block, FVG, Premium/Discount, CHoCH e BOS
  - Volume e fluxo (volume relativo, OBV, MFI, CMF, A/D)
  - Momentum (RSI de Wilder, MACD, ADX)
  - Tendência (EMAs, EMA200 e tendência semanal)
  - Contexto de mercado (IBOV e força relativa)
  - Score 0 a 100 em seis grupos, três modalidades de entrada, stop e alvos

Toda a lógica é escrita para "reversão de ALTA". A de baixa usa os preços e indicadores
espelhados (sinal invertido), então as duas direções usam exatamente o mesmo código.

Os pesos são INICIAIS, para testes. Não são probabilidades de acerto nem foram validados
estatisticamente: o backtest (backtest.py) é que diz o que funciona.
"""
import numpy as np
import pandas as pd

V2_DEFAULT = {
    "left": 5,
    "right": 3,
    "janela_sweep": 10,     # pregões
    "janela_div": 45,       # pregões
    "stop_atr": 0.5,        # margem do stop abaixo do fundo estrutural, em ATR
    "alvos_r": (1.5, 2.0, 3.0),
    "min_move_atr": 1.5,
}

# Perfis e tipos de sinal (as três decisões do projeto viram opções do app)
PERFIS = {
    "Conservador": {"min_score": 75, "modos": {"Confirmada", "Reteste"}, "aceita_semanal_contra": False},
    "Equilibrado": {"min_score": 60, "modos": {"Antecipada", "Confirmada", "Reteste"}, "aceita_semanal_contra": True},
    "Agressivo":   {"min_score": 45, "modos": {"Antecipada", "Confirmada", "Reteste"}, "aceita_semanal_contra": True},
}
TIPOS_SINAL = {
    "dois": {"Antecipada", "Confirmada", "Reteste"},
    "antecipado": {"Antecipada"},
    "confirmado": {"Confirmada", "Reteste"},
}
PRIORIDADE_MODO = ["Reteste", "Confirmada", "Antecipada"]


# ==================== INDICADORES ====================
def rsi_wilder(close, n=14):
    d = close.diff()
    up = d.clip(lower=0)
    dn = (-d).clip(lower=0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 - 100 / (1 + au / ad)


def adicionar_indicadores_v2(df):
    """Acrescenta RSI_W, OBV, MFI, CMF, AD, MACD_H, ADX e EMA200 (todos causais)."""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"].astype(float)
    df["RSI_W"] = rsi_wilder(c)
    df["OBV"] = (np.sign(c.diff()).fillna(0) * v).cumsum()

    tp = (h + l + c) / 3
    raw = tp * v
    pos = raw.where(tp > tp.shift(1), 0.0)
    neg = raw.where(tp < tp.shift(1), 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        df["MFI"] = 100 - 100 / (1 + pos.rolling(14).sum() / neg.rolling(14).sum())

    rng = (h - l).replace(0, np.nan)
    mfm = (((c - l) - (h - c)) / rng).fillna(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        df["CMF"] = (mfm * v).rolling(20).sum() / v.rolling(20).sum()
    df["AD"] = (mfm * v).cumsum()

    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["MACD_H"] = macd - macd.ewm(span=9, adjust=False).mean()

    up, dn = h.diff(), -l.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    a = 1 / 14
    trs = tr.ewm(alpha=a, adjust=False, min_periods=14).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * plus.ewm(alpha=a, adjust=False, min_periods=14).mean() / trs
        mdi = 100 * minus.ewm(alpha=a, adjust=False, min_periods=14).mean() / trs
        dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    df["ADX"] = dx.ewm(alpha=a, adjust=False, min_periods=14).mean()

    df["EMA200"] = c.ewm(span=200, adjust=False, min_periods=100).mean()
    if "Vol_MA" not in df:
        df["Vol_MA"] = v.rolling(20).mean()
    return df


def tendencia_semanal(df):
    """'Alta', 'Baixa' ou 'Lateral', pela EMA20 semanal (usa só dados até a última barra)."""
    try:
        w = df["Close"].resample("W").last().dropna()
    except Exception:
        return "Lateral"
    if len(w) < 25:
        return "Lateral"
    e = w.ewm(span=20, adjust=False).mean()
    c, slope = w.iloc[-1], e.iloc[-1] - e.iloc[-3]
    if c > e.iloc[-1] and slope > 0:
        return "Alta"
    if c < e.iloc[-1] and slope < 0:
        return "Baixa"
    return "Lateral"


def _sem_tz(idx):
    idx = pd.DatetimeIndex(idx)
    return idx.tz_localize(None) if idx.tz is not None else idx


def alinhar_mercado(ibov_df, index):
    """IBOV (Close, EMA20/50/200) alinhado ao índice do ativo; None se indisponível."""
    if ibov_df is None or len(ibov_df) < 60:
        return None
    try:
        c = ibov_df["Close"].astype(float).copy()
        c.index = _sem_tz(c.index)
        m = pd.DataFrame({"Close": c})
        m["EMA20"] = c.ewm(span=20, adjust=False).mean()
        m["EMA50"] = c.ewm(span=50, adjust=False).mean()
        m["EMA200"] = c.ewm(span=200, adjust=False, min_periods=100).mean()
        m = m[~m.index.duplicated(keep="last")].sort_index()
        return m.reindex(_sem_tz(index), method="ffill").reset_index(drop=True)
    except Exception:
        return None


# ==================== AUXILIARES ====================
def _gt(a, b):
    return bool(np.isfinite(a) and np.isfinite(b) and a > b)


def _arrays(df, direction):
    up = direction == "up"
    s = 1.0 if up else -1.0
    f = lambda k: df[k].values.astype(float)
    A = {
        "op": s * f("Open"), "cl": s * f("Close"),
        "hi": f("High") if up else -f("Low"),
        "lo": f("Low") if up else -f("High"),
        "pl": df["PL"].values if up else df["PH"].values,
        "ph": df["PH"].values if up else df["PL"].values,
        "vol": f("Volume"), "volma": f("Vol_MA"), "atr": f("ATR"),
        "ema20": s * f("EMA20"), "ema50": s * f("EMA50"), "ema200": s * f("EMA200"),
        "rsi": f("RSI_W") if up else 100 - f("RSI_W"),
        "obv": s * f("OBV"), "mfi": f("MFI") if up else 100 - f("MFI"),
        "cmf": s * f("CMF"), "ad": s * f("AD"), "macdh": s * f("MACD_H"), "adx": f("ADX"),
    }
    return A, s


def _swings(pl_flag, ph_flag, lo, hi):
    """Pivôs consolidados e alternados: [(indice, 'L'|'H'), ...]."""
    eventos = sorted([(int(p), "L") for p in np.where(pl_flag)[0]] +
                     [(int(p), "H") for p in np.where(ph_flag)[0]])
    sw = []
    for p, t in eventos:
        if sw and sw[-1][1] == t:
            q = sw[-1][0]
            if (t == "L" and lo[p] < lo[q]) or (t == "H" and hi[p] > hi[q]):
                sw[-1] = (p, t)
        else:
            sw.append((p, t))
    return sw


def _detectar_sweep(lo, cl, lows, n, right, janela):
    """Sweep: um candle perfura (com o pavio) o último fundo confirmado e fecha de volta
    acima dele, sem nenhum fechamento abaixo do fundo no intervalo. Devolve o mais recente."""
    achado = None
    for t in range(max(1, n - janela), n):
        cand = [q for q in lows if q + right < t]
        if not cand:
            continue
        q = cand[-1]
        nv = lo[q]
        if lo[t] < nv - 0.001 * abs(nv) and cl[t] > nv and (t - q - 1 <= 0 or cl[q + 1:t].min() >= nv):
            achado = (t, q, float(nv))
    return achado


def _par_divergencia(lo, lows, n, janela, min_sep=5):
    """Par de fundos confirmados (a, b) em que b é fundo MAIS BAIXO e separado de a."""
    for i in range(len(lows) - 1, 0, -1):
        b = lows[i]
        if b < n - janela:
            break
        a = lows[i - 1]
        if b - a >= min_sep and lo[b] < lo[a] - 0.001 * abs(lo[a]):
            return a, b
    return None


def _fvg(hi, lo, cl, n, a_now, base, janela=30):
    """FVG de alta ainda não preenchido (o mais recente), dentro da recuperação."""
    ini = max(2, n - janela, base or 0)
    achado = None
    for i in range(ini, n):
        g_lo, g_hi = hi[i - 2], lo[i]
        if g_hi - g_lo >= 0.3 * a_now and (i + 1 >= n or cl[i + 1:].min() > g_lo):
            achado = (i, float(g_lo), float(g_hi))
    return achado


def _classe(score, confirmada_estrutural, semanal_contra):
    aj = 10 if semanal_contra else 0
    if score < 40:
        c = "Sem oportunidade"
    elif score < 60:
        c = "Observação"
    elif score < 75 + aj:
        c = "Reversão em formação"
    elif score < 90 + aj:
        c = "Reversão confirmada"
    else:
        c = "Reversão de alta qualidade"
    # Regra fundamental: score alto não substitui a confirmação estrutural.
    if c in ("Reversão confirmada", "Reversão de alta qualidade") and not confirmada_estrutural:
        c = "Reversão em formação"
    return c


# ==================== AVALIAÇÃO ====================
def avaliar(df, direction, est, p=None, mercado=None, semanal=None):
    """Avalia a reversão na ÚLTIMA barra de df (que deve conter só dados já disponíveis).

    est: resultado de analyze_structure (com l0/l1) para a mesma direção.
    mercado: DataFrame do IBOV alinhado ao índice de df (ver alinhar_mercado) ou None.
    Retorna dict com score, classe, modalidades, entrada, stop e alvos; ou None.
    """
    p = {**V2_DEFAULT, **(p or {})}
    n = len(df)
    if n < 120 or "RSI_W" not in df:
        return None
    A, sgn = _arrays(df, direction)
    op, hi, lo, cl, vol = A["op"], A["hi"], A["lo"], A["cl"], A["vol"]
    atr, volma = A["atr"], A["volma"]
    a_now = atr[-1]
    if not (np.isfinite(a_now) and a_now > 0):
        return None
    right = p["right"]

    swings = _swings(A["pl"], A["ph"], lo, hi)
    lows = [q for q, t in swings if t == "L"]

    etapa = int(est.get("etapa", 0)) if est else 0
    l0 = est.get("l0") if (est and etapa > 0) else None
    l1 = est.get("l1") if (est and etapa > 0) else None
    nivel_up = float(hi[l1:l0 + 1].max()) if (etapa >= 2 and l0 is not None and l1 is not None) else None
    j = (n - 1 - int(est["barras"])) if etapa == 3 else None

    # ---------- Sweep e tendência prévia ----------
    sw = _detectar_sweep(lo, cl, lows, n, right, p["janela_sweep"])
    if sw is not None and not cl[-1] > sw[2]:
        sw = None   # o preço voltou a fechar abaixo do nível varrido: sweep invalidado

    prev_ok = etapa > 0
    leg_atr = est.get("perna_atr") if est else None
    if sw is not None and not prev_ok:
        t_s = sw[0]
        ini = max(0, t_s - 40)
        a_s = atr[t_s]
        if np.isfinite(a_s) and a_s > 0:
            leg_atr = (hi[ini:t_s + 1].max() - lo[t_s]) / a_s
            antes = [q for q in lows if q < t_s]
            desc = len(antes) >= 2 and lo[antes[-1]] < lo[antes[-2]]
            abaixo = _gt(A["ema50"][t_s], cl[t_s])
            prev_ok = bool(leg_atr >= p["min_move_atr"] and (desc or abaixo))
    if not prev_ok:
        return None
    if etapa == 0 and sw is None:
        return None

    # ---------- Âncoras ----------
    if etapa >= 2:
        ancora, base_stop = l0, lo[l0]
    elif sw is not None:
        ancora, base_stop = sw[0], lo[sw[0]]
    else:                       # etapa 1
        ancora, base_stop = l0, lo[l0]
    ref_ll = l1 if (l1 is not None and etapa >= 2) else (sw[0] if sw is not None else l0)

    # ---------- Divergências (pivôs confirmados e separados) ----------
    par = _par_divergencia(lo, lows, n, p["janela_div"])
    div_rsi = div_obv = div_mfi = div_macd = False
    if par:
        a, b = par
        div_rsi = bool(np.isfinite(A["rsi"][a]) and np.isfinite(A["rsi"][b]) and A["rsi"][b] - A["rsi"][a] >= 1.0)
        div_obv = bool(np.isfinite(A["obv"][a]) and np.isfinite(A["obv"][b]) and A["obv"][b] > A["obv"][a])
        div_mfi = bool(np.isfinite(A["mfi"][a]) and np.isfinite(A["mfi"][b]) and A["mfi"][b] - A["mfi"][a] >= 1.0)
        div_macd = bool(np.isfinite(A["macdh"][a]) and np.isfinite(A["macdh"][b]) and A["macdh"][b] > A["macdh"][a])

    # ---------- Volume no evento ----------
    ev = j if j is not None else (sw[0] if sw is not None else (l0 if l0 is not None else n - 1))
    ev = int(min(max(ev, 1), n - 1))
    vm = volma[ev]
    rv = float(vol[max(0, ev - 1):ev + 2].mean() / vm) if (np.isfinite(vm) and vm > 0) else 1.0
    rv = min(rv, 3.0)   # um único candle atípico não domina a classificação

    evid, g = [], {}

    # ===== 1) Estrutura de mercado (25) =====
    s = {0: 0, 1: 7, 2: 13, 3: 18}[etapa] + 1.0     # +1: tendência prévia validada
    bos = False
    if etapa >= 2:
        dist = (lo[l0] - lo[l1]) / a_now
        s += 1.5 if dist >= 0.5 else 0
        s += 1.0 if (l0 - l1) >= 7 else 0
        s += 1.5 if (nivel_up - lo[l1]) / a_now >= 1.5 else 0
    if etapa == 3:
        for q in lows:
            if q > j and lo[q] > lo[l0] and cl[-1] > hi[j:q + 1].max():
                bos = True
                break
        s += 2 if bos else 0
        evid.append("CHoCH: fechou acima do topo estrutural")
        if bos:
            evid.append("BOS confirmado")
    elif etapa == 2:
        evid.append("Fundo ascendente formado")
    elif etapa == 1:
        evid.append("Novo fundo mais baixo com divergência (aviso)")
    g["Estrutura"] = min(s, 25)

    # ===== 2) Liquidez e SMC (20) =====
    s = 0.0
    sweep_barras = None
    if sw is not None:
        sweep_barras = n - 1 - sw[0]
        s += 8 if sweep_barras <= 5 else 6
        evid.append(f"Liquidity Sweep há {sweep_barras} barra(s)")
    ob = None
    k = None
    for q in range(ancora, max(0, ancora - 6), -1):
        if cl[q] < op[q]:
            k = q
            break
    if k is not None:
        z_lo, z_hi = float(lo[k]), float(hi[k])
        near = (lo[-3:].min() <= z_hi + 0.5 * a_now) and cl[-1] >= z_lo
        s += 4 if near else 1
        ob = (z_lo, z_hi)
        if near:
            evid.append("Preço na região do Order Block")
    fv = _fvg(hi, lo, cl, n, a_now, ref_ll)
    if fv is not None:
        s += 2
        if lo[-1] <= fv[2] + 0.25 * a_now and cl[-1] >= fv[1]:
            s += 2
            evid.append("Preço no FVG de alta")
        else:
            evid.append("FVG de alta aberto")
    pd_pos = None
    if ref_ll is not None:
        ini = max(0, ref_ll - 40)
        H = hi[ini:ref_ll + 1].max()
        L = min(lo[ref_ll], lo[ref_ll:].min())
        if H > L:
            pd_pos = float((cl[-1] - L) / (H - L))
            s += 4 if pd_pos <= 0.5 else 3 if pd_pos <= 0.62 else 1 if pd_pos <= 0.75 else 0
            if pd_pos <= 0.5:
                evid.append("Preço em região de desconto")
    g["Liquidez/SMC"] = min(s, 20)

    # ===== 3) Volume e fluxo (15) =====
    s = 5 if rv >= 1.8 else 4 if rv >= 1.4 else 2 if rv >= 1.1 else 0
    if rv >= 1.1:
        evid.append(f"Volume {rv:.1f}x a média")
    if div_obv:
        s += 4
        evid.append("Divergência no OBV")
    if div_mfi:
        s += 3
        evid.append("Divergência no MFI")
    cmf, ad = A["cmf"][-1], A["ad"]
    if np.isfinite(cmf) and cmf > 0:
        s += 2
        evid.append("CMF positivo")
    if n > 11 and ad[-1] > ad[-11]:
        s += 1
    g["Volume/Fluxo"] = min(s, 15)

    # ===== 4) Momentum e divergências (15) =====
    rsi = A["rsi"]
    s = 4 if div_rsi else 0
    if div_rsi:
        evid.append("Divergência no RSI")
    rsi_recent = rsi[-30:]
    if np.isfinite(rsi_recent).any() and np.nanmin(rsi_recent) <= 35:
        s += 1
    recross = any(np.isfinite(rsi[i - 1]) and np.isfinite(rsi[i]) and rsi[i - 1] < 30 <= rsi[i]
                  for i in range(max(1, n - 10), n))
    if recross:
        s += 1
        evid.append("RSI voltou acima de 30")
    mh = A["macdh"]
    m = 3 if div_macd else 0
    if n > 3 and np.isfinite(mh[-3:]).all() and mh[-1] > mh[-2] > mh[-3]:
        m += 1
    if any(np.isfinite(mh[i - 1]) and np.isfinite(mh[i]) and mh[i - 1] <= 0 < mh[i] for i in range(max(1, n - 5), n)):
        m += 1
    s += min(m, 5)
    adx_ref = np.nanmax(A["adx"][max(0, n - 40):]) if np.isfinite(A["adx"][max(0, n - 40):]).any() else np.nan
    s += 4 if (np.isfinite(adx_ref) and adx_ref >= 25) else 2 if (np.isfinite(adx_ref) and adx_ref >= 20) else 0
    g["Momentum"] = min(s, 15)

    # ===== 5) Tendência e médias (15) =====
    s = 0.0
    e20, e50, e200 = A["ema20"], A["ema50"], A["ema200"]
    s += 3 if _gt(cl[-1], e20[-1]) else 0
    s += 2 if (n > 4 and _gt(e20[-1], e20[-4])) else 0
    s += 2 if _gt(cl[-1], e50[-1]) else 0
    w = min(40, n)
    kk = n - w + int(np.argmin(lo[-w:]))
    if np.isfinite(e50[kk]) and atr[kk] > 0:
        stretch = (e50[kk] - lo[kk]) / atr[kk]
        s += 2 if stretch >= 2 else 1 if stretch >= 1 else 0
    s += 2 if _gt(cl[-1], e200[-1]) else 0
    semanal = semanal or "Lateral"
    fav = "Alta" if direction == "up" else "Baixa"
    if semanal == fav:
        s += 4
        alinh = "Alinhado"
    elif semanal == "Lateral":
        s += 2
        alinh = "Neutro"
    else:
        alinh = "Contra"
    evid.append(f"Semanal: {semanal} ({alinh.lower()})")
    g["Tendência/Médias"] = min(s, 15)

    # ===== 6) Contexto de mercado (10) =====
    mk_txt = "sem IBOV"
    if mercado is not None and len(mercado) >= n:
        mm = mercado.iloc[:n]
        ic = sgn * mm["Close"].values.astype(float)
        i20, i50, i200 = (sgn * mm[k_].values.astype(float) for k_ in ("EMA20", "EMA50", "EMA200"))
        s = 0.0
        s += 2 if _gt(ic[-1], i50[-1]) else 0
        s += 2 if (n > 4 and _gt(i20[-1], i20[-4])) else 0
        s += 2 if _gt(ic[-1], i200[-1]) else 0
        real_c = sgn * cl                       # preço real do ativo
        real_i = mm["Close"].values.astype(float)
        for per in (20, 60):
            if n > per and np.isfinite(real_i[-1 - per]) and real_i[-1 - per] > 0:
                rs = sgn * ((real_c[-1] / real_c[-1 - per] - 1) - (real_i[-1] / real_i[-1 - per] - 1))
                s += 2 if rs > 0 else 0
        mk_txt = "favorável" if s >= 6 else "neutro" if s >= 4 else "desfavorável"
        evid.append(f"Mercado (IBOV): {mk_txt}")
    else:
        s = 5.0   # sem dados do IBOV: neutro
    g["Mercado"] = min(s, 10)

    score = int(round(sum(g.values())))

    # ---------- Modalidades de entrada ----------
    modos = []
    antecipada = bool(sw is not None and etapa < 3 and (div_rsi or div_obv or div_mfi or recross))
    confirmada = bool(etapa == 3 and rv >= 1.0)
    if etapa == 3 and rv < 1.0:
        evid.append("Rompimento sem volume (sem alerta de confirmação)")
    reteste = bool(etapa == 3 and (n - 1 - j) >= 2 and lo[-3:].min() <= nivel_up + 0.5 * a_now
                   and cl[-1] >= nivel_up and cl[-1] > op[-1])
    if antecipada:
        modos.append("Antecipada")
    if confirmada:
        modos.append("Confirmada")
    if reteste:
        modos.append("Reteste")
    modo = next((m_ for m_ in PRIORIDADE_MODO if m_ in modos), "—")

    classe = _classe(score, etapa == 3, alinh == "Contra")

    # ---------- Entrada, stop e alvos (espaço "alta"; converte para preço real no fim) ----------
    entrada = float(cl[-1])
    stop = float(base_stop - p["stop_atr"] * a_now)
    risco = entrada - stop
    if risco <= 0:
        return None
    alvos = [entrada + k_ * risco for k_ in p["alvos_r"]]
    topo = hi[max(0, ref_ll - 40):ref_ll + 1].max() if ref_ll is not None else entrada
    rr_est = float(max(0.0, (topo - entrada) / risco))

    real = lambda x: None if x is None else round(float(sgn * x), 2)
    idx_pivo = ancora
    dt = lambda i: df.index[int(min(max(i, 0), n - 1))]
    evento_idx = j if j is not None else (sw[0] if sw is not None else ancora)

    return {
        "direcao": "Compra" if direction == "up" else "Venda",
        "score": score, "grupos": {k_: round(v_, 1) for k_, v_ in g.items()},
        "classe": classe, "etapa": etapa, "modo": modo, "modos": modos,
        "sweep": sw is not None, "sweep_barras": sweep_barras,
        "choch": etapa == 3, "bos": bos, "ob": None if ob is None else (real(ob[0]), real(ob[1])),
        "fvg": None if fv is None else (real(fv[1]), real(fv[2])),
        "pd_pos": None if pd_pos is None else round(pd_pos, 2),
        "div": {"rsi": div_rsi, "obv": div_obv, "mfi": div_mfi, "macd": div_macd},
        "vol_rel": round(rv, 2), "semanal": semanal, "alinhamento": alinh, "mercado": mk_txt,
        "entrada": real(entrada), "stop": real(stop), "alvos": [real(a_) for a_ in alvos],
        "risco_pct": round(100 * risco / abs(entrada), 2), "rr_estrutural": round(rr_est, 1),
        "nivel": real(nivel_up), "perna_atr": None if leg_atr is None else round(float(leg_atr), 1),
        "idx_pivo": int(idx_pivo), "idx_evento": int(evento_idx),
        "data_pivo": dt(idx_pivo), "data_confirmacao": dt(idx_pivo + right),
        "sinal_desde": dt(evento_idx),
        "evidencias": evid,
    }


def passa_filtro(res, perfil="Equilibrado", tipo="dois"):
    """Aplica o perfil de entrada e o tipo de sinal escolhidos no app."""
    if res is None:
        return False
    pf = PERFIS.get(perfil, PERFIS["Equilibrado"])
    if res["score"] < pf["min_score"]:
        return False
    if not pf["aceita_semanal_contra"] and res["alinhamento"] == "Contra":
        return False
    permitidos = TIPOS_SINAL.get(tipo, TIPOS_SINAL["dois"]) & pf["modos"]
    if res["modo"] == "—":
        return res["etapa"] >= 1 and tipo == "dois"     # só como acompanhamento
    return any(m in permitidos for m in res["modos"])
