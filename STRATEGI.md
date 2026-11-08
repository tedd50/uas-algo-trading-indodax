# Strategi tertulis — Trend Following EMA 20/50 + EMA 200 + ADX (kripto IDR, 1 jam)

Semua angka di bawah berasal dari `core/config.py` (satu-satunya tempat parameter didefinisikan;
bot dan backtest sama-sama mengimpornya).

## 1. Aturan lengkap

| Komponen | Aturan |
|---|---|
| Pasar | Indodax, pasangan IDR spot, **long-only** (tanpa short, margin, leverage) |
| Universe | 6 pasangan: BTC/IDR, XRP/IDR, ETH/IDR, DOGE/IDR, TRX/IDR, BNB/IDR (`data/universe.json`, kriteria di §3) |
| Timeframe | Candle 1 jam (`history_v2 tf=60`), hanya candle **tertutup** (`Time + 3600 ≤ server_time`) |
| Indikator | EMA(Close,20), EMA(Close,50), EMA(Close,200) — alpha 2/(n+1), seed nilai pertama. ADX(14) Wilder (alpha 1/14) |
| **Entry** | Pada close candle *t*: `Cross(EMA20, EMA50)` **dan** `Close > EMA200` **dan** `ADX(14) > 20`. `Cross(a,b)` = `a[t] > b[t]` dan `a[t-1] ≤ b[t-1]` |
| Syarat data entry | 200 candle terakhir kontigu dengan harga & volume > 0; candle tertutup terakhir ≤ 2 jam; order book tidak kosong; spread bid–ask ≤ 2% |
| **Exit** | Pada close candle *t*: `Cross(EMA50, EMA20)` (death cross). Tanpa stop-loss/target (sama dengan UTS) |
| Eksekusi | Bot: segera setelah candle tertutup, beli di **ask**, jual di **bid** order book live, menghabiskan level berikutnya bila perlu (harga rata-rata). Backtest: open candle *t+1* ± (median setengah spread + median slippage) hasil snapshot, dibulatkan ke kenaikan harga |
| Sinyal berulang | Beli hanya bila belum memegang pasangan itu; jual hanya bila memegang (ExRem). Sinyal beli yang gagal dieksekusi tidak diulang |
| **Sizing** | 15% ekuitas (kas + posisi dinilai di best bid) per posisi, dibatasi kas tersedia dan ≤ 5% nilai transaksi IDR 24 candle terakhir; kuantitas dibulatkan ke bawah ke `quantity_increment` (1e-8) |
| Prioritas | Bila sinyal beli > slot: ADX tertinggi lebih dulu (lalu nama pasangan) |
| Fee | Taker all-in **beli 0,20555%**, **jual 0,41555%** (halaman resmi, lebih mahal dari API 0,20%) |
| Minimum order | Rp25.000 |
| Modal | Rp100.000.000 virtual, compounding |

## 2. Risk management (ada di kode `core/engine.py`, `core/bot.py`)

| Kontrol | Nilai | Bukti di log |
|---|---|---|
| Batas posisi terbuka | maks 5 | `events` reject "slot posisi penuh" |
| Ukuran maks per posisi | 15% ekuitas | `orders.value` |
| Daily loss limit | ekuitas ≤ 97% ekuitas awal hari WIB → tidak ada entry baru sampai 00.00 WIB berikutnya | `events.daily_loss_halt` |
| Batas hari | 00.00 WIB = 17.00 UTC; equity harian = panggilan pertama setelah 00.00 WIB | `daily_equity` |
| Kill switch | flag storage `uas:killswitch` (via `POST /api/admin?action=kill_on/kill_off`) atau env `KILL_SWITCH=1`; blokir entry baru, exit tetap jalan | `events.killswitch_*` |
| Retry terbatas | timeout 10 s, 3 percobaan, backoff 1 s/2 s; respons kosong = error | `errors.api_error` |
| Idempotency | `state.last_bar` + kunci `lock:<bar>` (SET NX EX 900) | `calls.status = already_processed / duplicate_locked` |
| Validasi data | lihat "Syarat data entry" | `events.validation` |

## 3. Universe & survivorship bias

Kriteria ditetapkan sebelum backtest (`scripts/select_universe.py`):
1. Kandidat = semua pasangan IDR di `/api/pairs` kecuali aset ber-peg (stablecoin, token emas).
2. Likuiditas diukur **pada awal periode backtest**: jendela 90 hari 3 Agu – 31 Okt 2023, candle harian.
3. Wajib aktif ≥ 85 dari 90 hari; ranking median nilai transaksi harian (close × volume); ambil 6 teratas.
Ranking lengkap: `data/universe_ranking.csv`.

Bias sisa: `/api/pairs` hanya berisi pasangan yang masih terdaftar sekarang, jadi pasangan yang
sudah delisting setelah 2023 tidak bisa ikut kandidat. Karena 6 teratas di 2023 adalah aset
berkapitalisasi besar yang tetap aktif, dampaknya kecil, tetapi tetap dicatat.

## 4. Perubahan dari versi UTS

Strategi UTS: saham Kompas100 harian, EMA 20/50 + EMA200 + ADX(14)>20, death cross exit,
10 posisi × 10% ekuitas, eksekusi open t+1 ± 1 fraksi (lihat `docs/uts/`).

| Aspek | UTS | UAS | Alasan |
|---|---|---|---|
| Pasar | IDX Kompas100 | Indodax IDR spot | ketentuan UAS |
| Timeframe | harian | **1 jam** | 10 hari harian = 10 candle → trade terlalu sedikit; soal menyarankan 1 jam/4 jam |
| Parameter EMA/ADX | 20/50/200, ADX14>20 | **tidak diubah** | menghindari overfitting; tidak ada optimasi ulang |
| Universe | 100 saham | 6 pasangan, likuiditas 2023 | aturan UAS 3–10 pasangan, anti-survivorship |
| Posisi | 10 × 10% | **5 × 15%** | universe hanya 6 pasangan |
| Lot | kelipatan 100 lembar | `quantity_increment` 1e-8, kenaikan harga per pasangan | aturan Indodax |
| Likuiditas | ≤ 5% nilai transaksi 20 hari | ≤ 5% nilai transaksi 24 jam | timeframe 1 jam |
| Biaya | fee broker + 1 fraksi | fee Indodax all-in + spread & slippage terukur dari snapshot | aturan UAS |
| Risk | tidak ada | daily loss limit 3%, kill switch, validasi data, idempotency | aturan UAS |

Semua perubahan ini selesai **sebelum** freeze (lihat README › Freeze).
