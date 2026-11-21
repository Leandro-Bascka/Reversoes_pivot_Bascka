"""Job automático: roda o scanner sem abrir o app e manda alertas ao Telegram.

Só alerta o que é NOVO, para cada sinal ser avisado uma única vez, sem precisar
guardar estado entre as execuções:
  - o pivô foi confirmado no último pregão (BarrasPivo == right), ou
  - a quebra de estrutura (etapa 3) aconteceu no último pregão (Barras == 0).

Variáveis de ambiente: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
Opcionais: TOP_N (30), MIN_VOL_MI (8), MIN_SCORE (7), LEFT (5), RIGHT (3),
           N_PIVOTS (2), TOL_PCT (0.3), MIN_MOVE_ATR (1.5),
           EXIGIR_TOPOS (1), EXIGIR_ESTRUTURA (1)
"""
import os
import sys

from scanner_core import run_scan, send_telegram, build_alert_message

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TOP_N = int(os.environ.get("TOP_N", 30))
MIN_VOL = float(os.environ.get("MIN_VOL_MI", 8)) * 1_000_000
MIN_SCORE = int(os.environ.get("MIN_SCORE", 7))
LEFT = int(os.environ.get("LEFT", 5))
RIGHT = int(os.environ.get("RIGHT", 3))

STRUCT = {
    "n_pivots": int(os.environ.get("N_PIVOTS", 2)),
    "tol": float(os.environ.get("TOL_PCT", 0.3)) / 100,
    "min_move_atr": float(os.environ.get("MIN_MOVE_ATR", 1.5)),
    "exigir_topos": os.environ.get("EXIGIR_TOPOS", "1") == "1",
    "exigir_estrutura": os.environ.get("EXIGIR_ESTRUTURA", "1") == "1",
}


def main():
    df, ranking = run_scan(left=LEFT, right=RIGHT, min_vol=MIN_VOL,
                           min_score=MIN_SCORE, top_n=TOP_N, struct=STRUCT)
    print(f"Universo líquido analisado: {len(ranking)} ativos")

    if df is None:
        print("Nenhum sinal.")
        return

    novos = df[(df["BarrasPivo"] == RIGHT) | ((df["Etapa"] == 3) & (df["Barras"] == 0))]
    print(f"{len(df)} sinais no total, {len(novos)} novos")

    if novos.empty:
        return

    msg = build_alert_message(novos.to_dict("records"), "Novas Reversões")
    print(f"TELEGRAM_TOKEN definido: {bool(TOKEN.strip())} | "
          f"TELEGRAM_CHAT_ID definido: {bool(CHAT_ID.strip())}")
    if send_telegram(msg, TOKEN, CHAT_ID, verbose=True):
        print("Alerta enviado.")
    else:
        print("Falha ao enviar alerta (confira os segredos).")
        sys.exit(1)


if __name__ == "__main__":
    main()
