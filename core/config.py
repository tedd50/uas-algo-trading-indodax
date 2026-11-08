"""Aturan, parameter, universe, biaya, dan risk management yang DIBEKUKAN.

Semua angka strategi ada di sini dan hanya di sini. Bot (Vercel) dan backtest
(laptop) sama-sama mengimpor modul ini, jadi tidak mungkin keduanya berbeda.
Setelah commit freeze, file ini tidak boleh diubah (lihat README > Freeze).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- strategi
# Parameter UTS dipertahankan apa adanya (tidak dioptimasi ulang untuk kripto).
STRATEGY_NAME = "Trend Following EMA 20/50 + filter EMA 200 + ADX(14) > 20 (long-only)"
FAST = 20          # EMA cepat
SLOW = 50          # EMA lambat
TREND = 200        # EMA filter tren
ADX_N = 14         # periode ADX (Wilder)
MIN_ADX = 20.0     # ADX minimum untuk entry

TIMEFRAME = "60"   # history_v2 tf (menit) -> candle 1 jam
TF_SECONDS = 3600

# Jendela indikator yang wajib lengkap (tanpa candle hilang) sebelum boleh entry.
VALID_WINDOW = TREND
# Jumlah bar yang diambil bot setiap panggilan. 3 halaman history_v2 (~1.900 bar)
# membuat EMA200/ADX konvergen (sisa efek seed < 1e-8) sehingga nilai indikator
# bot = nilai indikator backtest yang memakai riwayat 3 tahun.
BOT_HISTORY_PAGES = 3

# ---------------------------------------------------------------- universe
UNIVERSE_FILE = os.path.join(ROOT, "data", "universe.json")
BENCHMARK_PAIR = "btcidr"


def load_universe():
    with open(UNIVERSE_FILE) as f:
        return json.load(f)["pairs"]


# ---------------------------------------------------------------- modal & sizing
INITIAL_CAPITAL = 100_000_000.0   # Rp100 juta virtual
MAX_POSITIONS = 5                 # batas jumlah posisi terbuka
POSITION_PCT = 0.15               # ukuran target per posisi = 15% ekuitas
MAX_POSITION_PCT = 0.15           # ukuran maksimum per posisi (hard cap) = 15% ekuitas
LIQ_CAP_PCT = 0.05                # order <= 5% nilai transaksi IDR 24 bar terakhir
LIQ_LOOKBACK = 24

# ---------------------------------------------------------------- risk management
DAILY_LOSS_LIMIT = 0.03           # ekuitas turun >= 3% dari ekuitas awal hari WIB -> stop entry
WIB_OFFSET = 7 * 3600             # hari berganti 00.00 WIB = 17.00 UTC
MAX_STALE_BARS = 2                # candle tertutup terakhir maks 2x timeframe
MAX_SPREAD = 0.02                 # selisih bid-ask > 2% -> tidak buka posisi

# ---------------------------------------------------------------- biaya (diakses 8 Nov 2026)
# /api/pairs  trade_fee_percent_taker = 0.2 (semua pasangan IDR)
#   https://indodax.com/api/pairs  (salinan: docs/evidence/api_pairs_2026-11-08.json)
# Halaman resmi "Rincian Biaya Transaksi di INDODAX" (berlaku 1 Okt 2026), IDR Market PRO, Taker all-in:
#   BUY 0,20555% (service 0,20% + pajak 0% + CFX 0,00555%)
#   SELL 0,41555% (service 0,20% + pajak 0,21% + CFX 0,00555%)
#   https://help.indodax.com/hc/id/articles/4416646599705-Rincian-Biaya-Transaksi-di-INDODAX
#   (tabel: docs/evidence/indodax_fee_table_2026-11-08.jpg)
# Aturan soal: pakai yang lebih mahal -> halaman resmi (lebih mahal di kedua sisi).
FEE_API_TAKER = 0.0020
FEE_BUY = 0.0020555
FEE_SELL = 0.0041555
# Minimum order: /api/pairs trade_min_base_currency = Rp10.000; halaman resmi: order
# langsung di PRO minimal Rp25.000 -> pakai yang lebih ketat.
MIN_ORDER_IDR = 25_000.0

# ---------------------------------------------------------------- biaya eksekusi backtest
COSTS_FILE = os.path.join(ROOT, "data", "costs.json")   # median spread & slippage dari snapshot


def load_costs():
    with open(COSTS_FILE) as f:
        return json.load(f)


# ---------------------------------------------------------------- periode
BACKTEST_START = "2023-11-01T00:00:00Z"   # >= 3 tahun sebelum forward test
HISTORY_START = "2023-07-15T00:00:00Z"    # + pemanasan indikator (> 1.900 bar)
UNIVERSE_LOOKBACK_START = "2023-08-03T00:00:00Z"  # likuiditas diukur 90 hari sebelum BACKTEST_START

# Diisi pada commit freeze (UTC, ISO). None = belum dibekukan.
FREEZE_UTC = None
FORWARD_START_UTC = None
FORWARD_END_UTC = None
