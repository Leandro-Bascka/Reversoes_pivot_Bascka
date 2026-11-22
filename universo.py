"""Universo de ativos: lê a lista TICKERS do scanner_core.py, normaliza e remove duplicados.

Assim você pode editar a lista no scanner_core.py (com ou sem o sufixo .SA, em qualquer ordem,
até com repetidos) e o app, o job de alertas e o backtest usam sempre a mesma lista limpa.
"""
from scanner_core import TICKERS


def normalizar_tickers(lista):
    vistos, saida = set(), []
    for t in lista:
        t = str(t).strip().upper()
        if not t:
            continue
        if "." not in t and not t.startswith("^"):
            t += ".SA"
        if t not in vistos:
            vistos.add(t)
            saida.append(t)
    return saida


def carregar_universo():
    return normalizar_tickers(TICKERS)


def limite(valor, universo):
    """0, vazio ou negativo = todos os ativos da lista."""
    try:
        v = int(valor)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else len(universo)
