"""Job automático: roda o scanner sem abrir o app e manda alertas ao Telegram.

Alerta só o que é NOVO (cada sinal é avisado uma única vez, sem guardar estado):
  - V1 (pivôs): pivô confirmado no último pregão, ou quebra de estrutura que acabou de acontecer;
  - V2 (Bascka Reversal): modalidade de entrada que ficou verdadeira hoje e não valia ontem.
Também registra os sinais novos em data/historico_sinais.csv e atualiza os resultados dos antigos.

Variáveis de ambiente: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
Opcionais: TOP_N (0 = todos os ativos da lista), MIN_VOL_MI (8), MIN_SCORE (7), LEFT (5), RIGHT (3),
           N_PIVOTS (2), TOL_PCT (0.3), MIN_MOVE_ATR (1.5), EXIGIR_TOPOS (1), EXIGIR_ESTRUTURA (1),
           USAR_V1 (1), USAR_V2 (1), PERFIL (Equilibrado), TIPO_SINAL (dois|antecipado|confirmado),
           HISTORICO (data/historico_sinais.csv), ENVIAR_TODOS (0)
"""
import os
import sys

from scanner_core import (run_scan_full, send_telegram, build_alert_message, build_alert_message_v2)
import historico
from universo import carregar_universo, limite

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

UNIVERSO = carregar_universo()
TOP_N = limite(os.environ.get("TOP_N", 0), UNIVERSO)   # 0 = todos os ativos da lista
MIN_VOL = float(os.environ.get("MIN_VOL_MI", 8)) * 1_000_000
MIN_SCORE = int(os.environ.get("MIN_SCORE", 7))
ENVIAR_TODOS = os.environ.get("ENVIAR_TODOS", "0") == "1"   # 1 = envia todos os sinais atuais
LEFT = int(os.environ.get("LEFT", 5))
RIGHT = int(os.environ.get("RIGHT", 3))
USAR_V1 = os.environ.get("USAR_V1", "1") == "1"
USAR_V2 = os.environ.get("USAR_V2", "1") == "1"
PERFIL = os.environ.get("PERFIL", "Equilibrado")
TIPO = os.environ.get("TIPO_SINAL", "dois")
HISTORICO = os.environ.get("HISTORICO", "data/historico_sinais.csv")

STRUCT = {
    "n_pivots": int(os.environ.get("N_PIVOTS", 2)),
    "tol": float(os.environ.get("TOL_PCT", 0.3)) / 100,
    "min_move_atr": float(os.environ.get("MIN_MOVE_ATR", 1.5)),
    "exigir_topos": os.environ.get("EXIGIR_TOPOS", "1") == "1",
    "exigir_estrutura": os.environ.get("EXIGIR_ESTRUTURA", "1") == "1",
}


def enviar_em_lotes(rows, montar, titulo, tamanho):
    """Telegram limita cada mensagem a ~4096 caracteres: envia em lotes. Retorna True se tudo ok."""
    ok = True
    for i in range(0, len(rows), tamanho):
        if not send_telegram(montar(rows[i:i + tamanho], titulo), TOKEN, CHAT_ID, verbose=True):
            ok = False
    return ok


def main():
    out = run_scan_full(left=LEFT, right=RIGHT, min_vol=MIN_VOL, min_score=MIN_SCORE, top_n=TOP_N,
                        tickers=UNIVERSO, struct=STRUCT, perfil=PERFIL, tipo=TIPO, usar_v2=USAR_V2)
    print(f"Universo líquido analisado: {len(out['ranking'])} ativos | IBOV: "
          f"{'ok' if out.get('ibov_ok') else 'indisponível (contexto de mercado neutro)'}")
    analisados = {t for t, _ in out["ranking"]}
    fora = [t.replace(".SA", "") for t in UNIVERSO if t not in analisados]
    if fora:
        print(f"Fora da análise ({len(fora)}): {', '.join(fora)} "
              f"(sem dados no Yahoo, abaixo do volume mínimo ou cortados por TOP_N)")
    print(f"TELEGRAM_TOKEN definido: {bool(TOKEN.strip())} | "
          f"TELEGRAM_CHAT_ID definido: {bool(CHAT_ID.strip())}")

    falhou = False
    df1, df2 = out["v1"], out["v2"]

    # ---------- V2: histórico (registrar novos e resolver os antigos) ----------
    ja_avisados = set()
    if USAR_V2:
        try:
            ja_avisados = historico.ids_registrados(HISTORICO)    # antes de registrar os de hoje
            if df2 is not None:
                historico.registrar(HISTORICO, df2.to_dict("records"))
            historico.atualizar_resultados(HISTORICO, out["dfs"])
        except Exception as e:
            print(f"Histórico não atualizado: {type(e).__name__}: {e}")

    # ---------- V2: alertas ----------
    if USAR_V2:
        if df2 is None:
            print("V2: nenhum sinal.")
            enviar = None
        else:
            if ENVIAR_TODOS:
                enviar = df2
            else:
                # novos de hoje que ainda não foram avisados (o histórico evita reenvio ao rodar 2x no dia)
                novos = df2[df2["Novo"] & (df2["Modo"] != "—")]
                enviar = novos[[historico.id_sinal(r) not in ja_avisados for r in novos.to_dict("records")]]
            print(f"V2: {len(df2)} sinais no total, {len(enviar)} a enviar")
        if enviar is not None and not enviar.empty:
            titulo = "Bascka Reversal V2 — sinais atuais" if ENVIAR_TODOS else "Bascka Reversal V2 — novos sinais"
            falhou |= not enviar_em_lotes(enviar.to_dict("records"), build_alert_message_v2, titulo, 5)
        elif ENVIAR_TODOS:
            send_telegram("🎯 Bascka Reversal V2: nenhum sinal no momento.", TOKEN, CHAT_ID, verbose=True)

    # ---------- V1 (lógica original) ----------
    if USAR_V1:
        if df1 is None:
            print("V1: nenhum sinal.")
        else:
            if ENVIAR_TODOS:
                enviar1, titulo1 = df1, "Pivôs — sinais atuais"
            else:
                enviar1 = df1[(df1["BarrasPivo"] == RIGHT) | ((df1["Etapa"] == 3) & (df1["Barras"] == 0))]
                titulo1 = "Pivôs — novas reversões"
            print(f"V1: {len(df1)} sinais no total, {len(enviar1)} a enviar")
            if not enviar1.empty:
                falhou |= not enviar_em_lotes(enviar1.to_dict("records"), build_alert_message, titulo1, 6)

    if falhou:
        print("Falha ao enviar alerta (confira os segredos).")
        sys.exit(1)
    print("Concluído.")


if __name__ == "__main__":
    main()
