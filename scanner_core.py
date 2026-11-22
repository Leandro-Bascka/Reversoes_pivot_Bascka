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
    # "PETR4.SA", "PETR3.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA", "BBAS3.SA",
    # "B3SA3.SA", "WEGE3.SA", "ABEV3.SA", "ITSA4.SA", "RENT3.SA", "EQTL3.SA",
    # "PRIO3.SA", "SUZB3.SA", "RADL3.SA", "LREN3.SA", "BBSE3.SA", "GGBR4.SA",
    # "RAIL3.SA", "VIVT3.SA", "CSAN3.SA", "ENEV3.SA", "CMIG4.SA", "TOTS3.SA",
    # "HAPV3.SA", "EMBJ3.SA", "CSNA3.SA", "UGPA3.SA", "MBRF3.SA",
    # "KLBN11.SA", "SANB11.SA", "BPAC11.SA", "MULT3.SA", "CYRE3.SA", "ENGI11.SA",
    # "CPLE3.SA", "SBSP3.SA", "MOTV3.SA", "TIMS3.SA", "FLRY3.SA",
    # "HYPE3.SA", "MGLU3.SA", "ASAI3.SA", "AXIA3.SA", "VBBR3.SA", "RDOR3.SA",
    # "CSMG3.SA", "ALOS3.SA", "DIRR3.SA", "CURY3.SA", "PSSA3.SA", "BRAP4.SA",
    # "USIM5.SA", "CMIN3.SA", "GOAU4.SA", "MRVE3.SA", "EZTC3.SA", "IGTI11.SA"
    'AALR3.SA', 'ABCB4.SA', 'ABEV3.SA', 'AERI3.SA', 'AFLT3.SA', 'AGRO3.SA',
    'AGXY3.SA', 'AHEB3.SA', 'AHEB5.SA', 'AHEB6.SA', 'ALLD3.SA', 'ALOS3.SA',
    'ALPA3.SA', 'ALPA4.SA', 'ALPK3.SA', 'ALUP3.SA', 'ALUP4.SA', 'AMAR3.SA',
    'AMBP3.SA', 'AMER3.SA', 'AMOB3.SA', 'ANIM3.SA', 'ARML3.SA', 'ARND3.SA',
    'ASAI3.SA', 'ATED3.SA', 'AUAU3.SA', 'AURE3.SA', 'AVLL3.SA', 'AXIA3.SA',
    'AXIA7.SA', 'AZEV3.SA', 'AZEV4.SA', 'AZTE3.SA', 'AZUL3.SA', 'AZUL97.SA',
    'AZUL98.SA', 'AZUL99.SA', 'AZZA3.SA', 'B1003.SA', 'B3SA3.SA', 'BALM3.SA',
    'BALM4.SA', 'BAUH4.SA', 'BAZA3.SA', 'BBAS3.SA', 'BBDC3.SA', 'BBDC4.SA',
    'BBSE3.SA', 'BDLL3.SA', 'BDLL4.SA', 'BEEF3.SA', 'BEES3.SA', 'BEES4.SA',
    'BGIP3.SA', 'BGIP4.SA', 'BHIA3.SA', 'BIED3.SA', 'BIOM3.SA', 'BLAU3.SA',
    'BMEB3.SA', 'BMEB4.SA', 'BMGB4.SA', 'BMIN3.SA', 'BMIN4.SA', 'BMKS3.SA',
    'BMOB3.SA', 'BNBR3.SA', 'BOBR4.SA', 'BPAC3.SA', 'BPAC5.SA', 'BPAR3.SA',
    'BRAP3.SA', 'BRAP4.SA', 'BRAV3.SA', 'BRKM3.SA', 'BRKM5.SA', 'BRKM6.SA',
    'BRSR3.SA', 'BRSR5.SA', 'BRSR6.SA', 'BRST3.SA', 'BSLI3.SA', 'BSLI4.SA',
    'CALI3.SA', 'CAMB3.SA', 'CAML3.SA', 'CASH3.SA', 'CASN3.SA', 'CASN4.SA',
    'CBAV3.SA', 'CBEE3.SA', 'CCTY3.SA', 'CEAB3.SA', 'CEBR3.SA', 'CEBR5.SA',
    'CEBR6.SA', 'CEDO3.SA', 'CEDO4.SA', 'CEEB3.SA', 'CEEB5.SA', 'CEED3.SA',
    'CEED4.SA', 'CEGR3.SA', 'CGAS3.SA', 'CGAS5.SA', 'CGRA3.SA', 'CGRA4.SA',
    'CLSC3.SA', 'CLSC4.SA', 'CMIG3.SA', 'CMIG4.SA', 'CMIN3.SA', 'COCE3.SA',
    'COCE5.SA', 'COGN3.SA', 'CPFE3.SA', 'CPLE3.SA', 'CRPG3.SA', 'CRPG5.SA',
    'CRPG6.SA', 'CSAN3.SA', 'CSED3.SA', 'CSMG3.SA', 'CSNA3.SA', 'CSUD3.SA',
    'CTAX3.SA', 'CTKA3.SA', 'CTKA4.SA', 'CTNM4.SA', 'CTSA3.SA', 'CTSA4.SA',
    'CURY3.SA', 'CVCB3.SA', 'CXSE3.SA', 'CYRE3.SA', 'CYRE4.SA', 'DASA3.SA',
    'DESK3.SA', 'DEXP3.SA', 'DEXP4.SA', 'DIRR3.SA', 'DMVF3.SA', 'DOHL3.SA',
    'DOHL4.SA', 'DOTZ3.SA', 'DTCY3.SA', 'DXCO3.SA', 'EALT3.SA', 'EALT4.SA',
    'ECOM3.SA', 'ECOR3.SA', 'EGIE3.SA', 'EKTR3.SA', 'EKTR4.SA', 'EMBJ3.SA',
    'ENEV3.SA', 'ENGI3.SA', 'ENGI4.SA', 'ENJU3.SA', 'ENMT3.SA', 'ENMT4.SA',
    'EPAR3.SA', 'EQMA3B.SA', 'EQPA3.SA', 'EQPA5.SA', 'EQTL3.SA', 'ESPA3.SA',
    'ESTR4.SA', 'ETER3.SA', 'EUCA3.SA', 'EUCA4.SA', 'EVEN3.SA', 'EZTC3.SA',
    'FESA3.SA', 'FESA4.SA', 'FHER3.SA', 'FIEI3.SA', 'FIGE3.SA', 'FIQE3.SA',
    'FLRY3.SA', 'FRAS3.SA', 'FRIO3.SA', 'GEPA3.SA', 'GEPA4.SA', 'GFSA3.SA',
    'GGBR3.SA', 'GGBR4.SA', 'GGPS3.SA', 'GMAT3.SA', 'GOAU3.SA', 'GOAU4.SA',
    'GPAR3.SA', 'GRND3.SA', 'GSHP3.SA', 'HAGA3.SA', 'HAGA4.SA', 'HAPV3.SA',
    'HBOR3.SA', 'HBRE3.SA', 'HBSA3.SA', 'HBTS5.SA', 'HETA3.SA', 'HETA4.SA',
    'HOOT4.SA', 'HYPE3.SA', 'IFCM3.SA', 'IGTI3.SA', 'IGTI4.SA', 'INEP3.SA',
    'INEP4.SA', 'INTB3.SA', 'IRBR3.SA', 'ISAE3.SA', 'ISAE4.SA', 'ITSA3.SA',
    'ITSA4.SA', 'ITUB3.SA', 'ITUB4.SA', 'JALL3.SA', 'JFEN3.SA', 'JHSF3.SA',
    'JOPA3.SA', 'JOPA4.SA', 'JSLG3.SA', 'KEPL3.SA', 'KLBN3.SA', 'KLBN4.SA',
    'LAND3.SA', 'LAVV3.SA', 'LEVE3.SA', 'LIGT3.SA', 'LJQQ3.SA', 'LOGG3.SA',
    'LOGN3.SA', 'LPSB3.SA', 'LREN3.SA', 'LUPA3.SA', 'LUXM4.SA', 'LWSA3.SA',
    'MAPT3.SA', 'MATD3.SA', 'MBRF3.SA', 'MDIA3.SA', 'MDNE3.SA', 'MEAL3.SA',
    'MELK3.SA', 'MGEL4.SA', 'MGLU3.SA', 'MILS3.SA', 'MLAS3.SA', 'MMAQ3.SA',
    'MMAQ4.SA', 'MNDL3.SA', 'MNPR3.SA', 'MOTV3.SA', 'MOVI3.SA', 'MRVE3.SA',
    'MSPA3.SA', 'MSPA4.SA', 'MTRE3.SA', 'MTSA3.SA', 'MTSA4.SA', 'MULT3.SA',
    'MWET3.SA', 'MWET4.SA', 'MYPK3.SA', 'NATU3.SA', 'NEXP3.SA', 'NORD3.SA',
    'NUTR3.SA', 'OBTC3.SA', 'ODER4.SA', 'OFSA3.SA', 'ONCO3.SA', 'OPCT3.SA',
    'ORVR3.SA', 'OSXB3.SA', 'PASS3.SA', 'PATI3.SA', 'PATI4.SA', 'PCAR3.SA',
    'PDGR3.SA', 'PDTC3.SA', 'PEAB3.SA', 'PEAB4.SA', 'PETR3.SA', 'PETR4.SA',
    'PFRM3.SA', 'PGMN3.SA', 'PINE3.SA', 'PINE4.SA', 'PLAS3.SA', 'PLPL3.SA',
    'PMAM3.SA', 'PNVL3.SA', 'POMO3.SA', 'POMO4.SA', 'POSI3.SA', 'PRIO3.SA',
    'PRNR3.SA', 'PSSA3.SA', 'PTBL3.SA', 'QUAL3.SA', 'RADL3.SA', 'RAIL3.SA',
    'RAIZ4.SA', 'RANI3.SA', 'RAPT3.SA', 'RAPT4.SA', 'RCSL3.SA', 'RCSL4.SA',
    'RDOR3.SA', 'RECV3.SA', 'REDE3.SA', 'RENT3.SA', 'RENT4.SA', 'RIAA3.SA',
    'RNEW3.SA', 'RNEW4.SA', 'ROMI3.SA', 'RPAD3.SA', 'RPAD5.SA', 'RPAD6.SA',
    'RSID3.SA', 'RSUL4.SA', 'RVEE3.SA', 'SANB3.SA', 'SANB4.SA', 'SAPR3.SA',
    'SAPR4.SA', 'SAUD3.SA', 'SBFG3.SA', 'SBSP3.SA', 'SCAR3.SA', 'SEER3.SA',
    'SEQL3.SA', 'SHUL3.SA', 'SHUL4.SA', 'SIMH3.SA', 'SLCE3.SA', 'SMFT3.SA',
    'SMTO3.SA', 'SNSY3.SA', 'SNSY5.SA', 'SNSY6.SA', 'SOJA3.SA', 'SOND3.SA',
    'SOND5.SA', 'SOND6.SA', 'SUZB3.SA', 'SYNE3.SA', 'TAEE3.SA', 'TAEE4.SA',
    'TASA3.SA'
    'AAZQ11.SA', 'ABCP11.SA', 'ADSH11.SA', 'AERO11.SA', 'AFHI11.SA', 'AGRX11.SA',
    'AIEC11.SA', 'AJFI11.SA', 'ALMI11.SA', 'ALUP11.SA', 'ALZC11.SA', 'ALZR11.SA',
    'ANCR11.SA', 'APTO11.SA', 'APXM11.SA', 'APXR11.SA', 'APXU11.SA', 'AROA11.SA',
    'ARRI11.SA', 'ARTE11.SA', 'ASRF11.SA', 'ATSA11.SA', 'AURB11.SA', 'AVUR11.SA',
    'AZPL11.SA', 'BBFI11.SA', 'BBFO11.SA', 'BBGO11.SA', 'BBIG11.SA', 'BBRC11.SA',
    'BCIA11.SA', 'BCRI11.SA', 'BICE11.SA', 'BIME11.SA', 'BIPD11.SA', 'BIPE11.SA',
    'BLCA11.SA', 'BLMG11.SA', 'BLMO11.SA', 'BLOG11.SA', 'BMLC11.SA', 'BNFS11.SA',
    'BPAC11.SA', 'BPML11.SA', 'BRBI11.SA', 'BRCO11.SA', 'BRCR11.SA', 'BRIM11.SA',
    'BRIP11.SA', 'BROF11.SA', 'BTAL11.SA', 'BTHI11.SA', 'BTLG11.SA', 'BTML11.SA',
    'BTRA11.SA', 'BTRU11.SA', 'BTSI11.SA', 'BTWR11.SA', 'BTYU11.SA', 'BVAR11.SA',
    'CACR11.SA', 'CARE11.SA', 'CBOP11.SA', 'CCME11.SA', 'CCVA11.SA', 'CENU11.SA',
    'CEOC11.SA', 'CFII11.SA', 'CJCT11.SA', 'CLIN11.SA', 'CNES11.SA', 'CPLG11.SA',
    'CPOF11.SA', 'CPTR11.SA', 'CPTS11.SA', 'CPUR11.SA', 'CRAA11.SA', 'CRFF11.SA',
    'CTXT11.SA', 'CXAG11.SA', 'CXCE11.SA', 'CXCI11.SA', 'CXCO11.SA', 'CXRI11.SA',
    'CXTL11.SA', 'CYCR11.SA', 'CYLD11.SA', 'DAMA11.SA', 'DAMT11.SA', 'DCRA11.SA',
    'DEVA11.SA', 'DOVL11.SA', 'DPRO11.SA', 'DRIT11.SA', 'DVFF11.SA', 'DVLP11.SA',
    'EDFO11.SA', 'EDGA11.SA', 'EDGE11.SA', 'EGAF11.SA', 'EGDB11.SA', 'EGYR11.SA',
    'EIRA11.SA', 'EMET11.SA', 'ENGI11.SA', 'EQIR11.SA', 'ERPA11.SA', 'EURO11.SA',
    'EXES11.SA', 'FAED11.SA', 'FAMB11.SA', 'FATN11.SA', 'FCFL11.SA', 'FGAA11.SA',
    'FIGS11.SA', 'FIIB11.SA', 'FIIP11.SA', 'FISC11.SA', 'FIVN11.SA', 'FLCR11.SA',
    'FLMA11.SA', 'FLRP11.SA', 'FMOF11.SA', 'FPAB11.SA', 'FPNG11.SA', 'FTCE11.SA',
    'FVPQ11.SA', 'FZDA11.SA', 'GAME11.SA', 'GARE11.SA', 'GCDL11.SA', 'GCRA11.SA',
    'GCRI11.SA', 'GFDL11.SA', 'GGRC11.SA', 'GLCR11.SA', 'GLOG11.SA', 'GLPF11.SA',
    'GRAV11.SA', 'GRUL11.SA', 'GRWA11.SA', 'GSFI11.SA', 'GTWR11.SA', 'HAAA11.SA',
    'HABT11.SA', 'HBCR11.SA', 'HCHG11.SA', 'HCRI11.SA', 'HCST11.SA', 'HCTR11.SA',
    'HDEL11.SA', 'HDOF11.SA', 'HFOF11.SA', 'HGBL11.SA', 'HGBS11.SA', 'HGCR11.SA',
    'HGFF11.SA', 'HGIC11.SA', 'HGLG11.SA', 'HGPO11.SA', 'HGRE11.SA', 'HGRU11.SA',
    'HILG11.SA', 'HJCT11.SA', 'HLOG11.SA', 'HOFC11.SA', 'HOMS11.SA', 'HOSI11.SA',
    'HPDP11.SA', 'HRDF11.SA', 'HREC11.SA', 'HRES11.SA', 'HSAF11.SA', 'HSLG11.SA',
    'HSML11.SA', 'HTMX11.SA', 'HUCG11.SA', 'HUSC11.SA', 'HUSI11.SA', 'IAAG11.SA',
    'IAGR11.SA', 'IBBP11.SA', 'IBCR11.SA', 'ICNE11.SA', 'ICRI11.SA', 'IGTI11.SA',
    'INDE11.SA', 'INLG11.SA', 'INRD11.SA', 'IRIM11.SA', 'ITIP11.SA', 'ITIT11.SA',
    'ITRI11.SA', 'JASC11.SA', 'JFLL11.SA', 'JGPX11.SA', 'JPPA11.SA', 'JPRD11.SA',
    'JSAF11.SA', 'JSCR11.SA', 'JSRE11.SA', 'KCRE11.SA', 'KDOL11.SA', 'KEVE11.SA',
    'KFOF11.SA', 'KISU11.SA', 'KIVO11.SA', 'KLBN11.SA', 'KNCR11.SA', 'KNHF11.SA',
    'KNHY11.SA', 'KNIP11.SA', 'KNPR11.SA', 'KNRE11.SA', 'KNRI11.SA', 'KNSC11.SA',
    'KONG11.SA', 'KOPA11.SA', 'KORE11.SA', 'LAFI11.SA', 'LASC11.SA', 'LIFE11.SA',
    'LKDV11.SA', 'LLAO11.SA', 'LPLP11.SA', 'LRDI11.SA', 'LRED11.SA', 'LSAG11.SA',
    'LSOI11.SA', 'LSOP11.SA', 'LTMT11.SA', 'LVBI11.SA', 'MANA11.SA', 'MAXR11.SA',
    'MCCI11.SA', 'MFII11.SA', 'MGHT11.SA', 'MIDW11.SA', 'MMPD11.SA', 'MMVE11.SA',
    'MXRF11.SA', 'NAUI11.SA', 'NCRI11.SA', 'NEWL11.SA', 'NEWU11.SA', 'NEXG11.SA',
    'NSLU11.SA', 'NVHO11.SA', 'OCRE11.SA', 'OIAG11.SA', 'OUJP11.SA', 'PABY11.SA',
    'PATA11.SA', 'PATC11.SA', 'PATL11.SA', 'PDBM11.SA', 'PEMA11.SA', 'PLCA11.SA',
    'PLRI11.SA', 'PMFO11.SA', 'PMIS11.SA', 'PNCR11.SA', 'PNDL11.SA', 'PNPR11.SA',
    'PNRC11.SA', 'PORD11.SA', 'PQAG11.SA', 'PQDP11.SA', 'PRSN11.SA', 'PRSV11.SA',
    'PVBI11.SA', 'RBDS11.SA', 'RBFM11.SA', 'RBFY11.SA', 'RBHG11.SA', 'RBHY11.SA',
    'RBIR11.SA', 'RBOP11.SA', 'RBRD11.SA', 'RBRF11.SA', 'RBRI11.SA', 'RBRK11.SA',
    'RBRL11.SA', 'RBRP11.SA', 'RBRR11.SA', 'RBRS11.SA', 'RBRX11.SA', 'RBRY11.SA',
    'RBTS11.SA', 'RBVA11.SA', 'RCFA11.SA', 'RCFF11.SA', 'RCRB11.SA', 'RCRI11.SA',
    'RDLI11.SA', 'RECM11.SA', 'RECR11.SA', 'RECT11.SA', 'REIT11.SA', 'REME11.SA',
    'RENV11.SA', 'RFOF11.SA', 'RINV11.SA', 'RMBS11.SA', 'RNDP11.SA', 'RNGO11.SA',
    'ROOF11.SA', 'RPRI11.SA', 'RSPD11.SA', 'RZAG11.SA', 'RZAK11.SA', 'RZAT11.SA',
    'RZTR11.SA', 'RZZI11.SA', 'SANB11.SA', 'SAPI11.SA', 'SAPR11.SA', 'SARE11.SA',
    'SCPF11.SA', 'SEED11.SA', 'SEQR11.SA', 'SHPH11.SA', 'SHPP11.SA', 'SJAU11.SA',
    'SNAG11.SA', 'SNCI11.SA', 'SNEL11.SA', 'SNFF11.SA', 'SNFZ11.SA', 'SNME11.SA',
    'SOFF11.SA', 'SOLR11.SA', 'SPDE11.SA', 'SPG211.SA', 'SPTW11.SA', 'SPXS11.SA',
    'STRX11.SA', 'STYI11.SA', 'TAEE11.SA'
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
