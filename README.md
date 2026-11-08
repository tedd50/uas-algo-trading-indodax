# UAS Algoritma Trading — Bot Dry Run Indodax di Vercel

Bot trading **dry run** (order disimulasikan, tanpa API key, tanpa uang sungguhan) yang menjalankan
strategi trend-following UTS pada pasar kripto IDR Indodax, berjalan di Vercel tiap candle 1 jam,
plus backtest ≥ 3 tahun dengan data historis asli Indodax dan dashboard pembanding.

- Mahasiswa: Aci Yuliawati · NIM 25120200012 *(sesuai berkas UTS di `docs/uts/` — verifikasi)*
- Soal: Soal UAS Algoritma Trading — Bot Dry Run Indodax di Vercel (berkas dosen, tidak disertakan di repo publik)
- Strategi tertulis + perubahan dari UTS: [`STRATEGI.md`](STRATEGI.md)
- Refleksi: [`REFLEKSI.md`](REFLEKSI.md) (ikut tampil di dashboard)
- Link Vercel (dashboard): https://uas-algo-trading-indodax.vercel.app · Repo: https://github.com/tedd50/uas-algo-trading-indodax

## Freeze

| Item | Nilai |
|---|---|
| Waktu freeze (UTC / WIB) | 2026-11-08 15:20 UTC / 8 Nov 2026 22.20 WIB (`core/config.py` `FREEZE_UTC`) |
| Commit freeze | commit bertag **`freeze`** — `git show freeze` (hash & waktu commit ada di riwayat GitHub) |
| Forward test | 2026-11-08 16:00 UTC → 2026-11-18 16:00 UTC (23.00 WIB → 23.00 WIB), 10 hari penuh = 240 candle 1 jam |
| Data & biaya saat freeze | candle s.d. bar 2026-11-08 14:00 UTC; spread/slippage = median snapshot sebelum `FREEZE_UTC` (`data/costs.json`) |
| Yang dibekukan | `core/config.py` (parameter, sizing, risk, fee), `core/strategy.py`, `core/engine.py`, `core/execution.py`, `data/universe.json`, `data/costs.json` |

Setelah commit freeze, file di atas tidak diubah. Perbaikan bug yang tidak mengubah aturan dicatat
lewat `POST /api/admin?action=note&msg=...` (masuk log `events`) dan di tabel *Catatan perbaikan* di bawah.
Riwayat commit tidak boleh ditulis ulang (tanpa force-push).

> **Catatan jadwal (jujur):** jadwal soal menetapkan freeze Rabu 4 Nov 2026 12.00 WIB dan forward test
> s.d. 14 Nov. Repositori ini baru selesai 8 Nov 2026, jadi freeze dilakukan pada waktu commit freeze yang
> sebenarnya (tanggal **tidak** diundurkan) dan forward test tetap dijalankan 10 hari penuh sampai
> 18 Nov 2026, sehingga pengumpulan terlambat dari tenggat. Bot mengabaikan candle yang tertutup sebelum
> `FORWARD_START_UTC` (status `before_forward_start`), sehingga state awal bot = state awal backtest ulang.

Catatan perbaikan selama forward test: *(belum ada)*

## Struktur

```
core/            kode BERSAMA bot & backtest
  config.py      semua parameter, universe, fee, risk (dibekukan)
  strategy.py    compute_signals(): EMA/ADX + sinyal entry/exit (satu fungsi untuk bot & backtest)
  engine.py      step(): sizing, risk management, daily loss, kill switch, eksekusi
  execution.py   walk order book (bot) & model biaya (backtest), pembulatan, fee
  bot.py         satu tick: state → data → validasi → sinyal → eksekusi → simpan log
  backtest.py    backtest event-driven per candle memakai engine yang sama
  indodax.py     klien API publik (timeout, retry terbatas, ≤ 3 req/detik)
  store.py       Upstash Redis REST (Vercel) / folder lokal (uji)
  analysis.py    metrik forward, uptime, gap backtest-vs-forward
  metrics.py     return, CAGR, MDD, PF, win rate, porsi biaya
  report.py      render dashboard HTML mandiri (SVG inline, tanpa internet)
api/             fungsi Vercel: tick, dashboard, logs, admin, health
scripts/         dijalankan di laptop: select_universe, fetch_history, collect_snapshots,
                 estimate_costs, backtest, export_logs, hitung_ulang, run_tick_local
data/            universe.json, universe_ranking.csv, costs.json, candles/ (CSV), snapshots/ (JSONL mentah)
results/         backtest_summary.json (dibaca dashboard Vercel), backtest_*.csv, hitung_ulang_metrics.json
logs/            log mentah forward test (JSONL) hasil export_logs
dashboard/       dashboard_offline.html (mandiri, bisa dibuka tanpa internet)
tests/           uji unit (offline) + replay_test.py (uji integrasi di candle historis)
docs/            soal, berkas UTS, bukti fee (screenshot tabel resmi & salinan /api/pairs)
```

## Biaya, minimum order, data (diakses 8 Nov 2026)

| Item | API | Halaman resmi | Dipakai |
|---|---|---|---|
| Fee taker IDR | `trade_fee_percent_taker` = 0,2% — https://indodax.com/api/pairs (salinan `docs/evidence/api_pairs_2026-11-08.json`) | Beli 0,20555%, jual 0,41555% all-in (service 0,20% + pajak 0/0,21% + CFX 0,00555%), berlaku 1 Okt 2026 — https://help.indodax.com/hc/id/articles/4416646599705-Rincian-Biaya-Transaksi-di-INDODAX (`docs/evidence/indodax_fee_table_2026-11-08.jpg`) | **yang lebih mahal: 0,20555% / 0,41555%** |
| Minimum order | `trade_min_base_currency` = Rp10.000 | order langsung di PRO minimal Rp25.000 | **Rp25.000** |
| Kenaikan harga / qty | https://indodax.com/api/price_increments, `quantity_increment` | — | per pasangan, `data/universe.json` |
| Batas API | 180 request/menit | — | ≤ 3 request/detik, tanpa paralel |

Spread & slippage backtest = median dari snapshot order book (`data/snapshots/`, dikumpulkan tiap jam
sejak 8 Nov 2026) untuk order acuan Rp15 juta. Selama forward test bot menyimpan snapshot mentah setiap
panggilan (log `snapshots`), dan dashboard membandingkan angka backtest dengan seluruh snapshot.

## Menjalankan di laptop (Python 3.10+, tanpa dependensi)

```bash
python3 -m unittest discover -s tests -v                       # uji unit offline
python3 scripts/select_universe.py                            # universe dari likuiditas 2023
python3 scripts/fetch_history.py                              # candle 1 jam sejak Jul 2023 (tarik mundur)
python3 scripts/collect_snapshots.py --every 3600 --count 72  # snapshot order book tiap jam
python3 scripts/estimate_costs.py --until <FREEZE_UTC>        # median spread/slippage → data/costs.json
python3 scripts/backtest.py --end <FREEZE_UTC>                # backtest ≥ 3 tahun → results/
python3 scripts/run_tick_local.py --twice                     # satu tick live + uji idempotency (storage lokal)
python3 tests/replay_test.py --hours 240 --out /tmp/replay    # uji integrasi: sinyal bot == backtest
```

## Deploy ke Vercel

1. Push repo ke GitHub (publik), lalu Vercel → *Add New Project* → import repo (framework: *Other*).
2. Vercel → *Storage* / *Marketplace* → **Upstash Redis** (gratis) → hubungkan ke proyek
   (mengisi `KV_REST_API_URL`, `KV_REST_API_TOKEN` otomatis).
3. *Settings → Environment Variables*: `CRON_SECRET` = string acak ≥ 32 karakter
   (mis. `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`), `KEY_PREFIX=uas`. Redeploy.
4. Uji koneksi Vercel → Indodax & storage:
   `curl -H "Authorization: Bearer $CRON_SECRET" https://<proyek>.vercel.app/api/health`
5. Penjadwal (timeframe 1 jam; Vercel Cron Hobby hanya 1×/hari):
   - **GitHub Actions** `.github/workflows/tick.yml` — menit 7, 22, 37, 52 tiap jam. Isi *repo secrets*
     `TICK_URL=https://<proyek>.vercel.app/api/tick` dan `CRON_SECRET`.
   - Disarankan cadangan **cron-job.org** (gratis): URL yang sama, metode POST, header
     `Authorization: Bearer <CRON_SECRET>`, jadwal menit 9 tiap jam, URL `.../api/tick?src=cronjob-org`.
   - `vercel.json` juga memasang Vercel Cron harian 00.17 UTC sebagai cadangan terakhir.
   Banyak pemanggil aman karena idempotency: candle yang sama hanya diproses sekali.
6. *Opsional:* `.github/workflows/export-logs.yml` menyalin log ke `logs/` setiap hari
   (secret `DASHBOARD_URL`), sehingga log juga terekam di riwayat commit.

Endpoint:

| Endpoint | Akses | Fungsi |
|---|---|---|
| `POST /api/tick` | `CRON_SECRET` | satu siklus bot |
| `GET /` atau `/api/dashboard` | publik | dashboard (membaca log storage; cache 20 menit, `?refresh=1`) |
| `GET /api/logs?name=<log>&start=&end=` | publik, read-only | log mentah JSON (tanpa secret) |
| `POST /api/admin?action=kill_on` / `kill_off` / `note&msg=` · `GET ?action=status` | `CRON_SECRET` | kill switch & catatan, tanpa deploy ulang |
| `GET /api/health` | `CRON_SECRET` | uji koneksi Indodax & storage |

### Uji koneksi sebelum freeze (8 Nov 2026, ±15.04 UTC)

- `GET /api/health` dari fungsi Vercel: `indodax_ok: true` (server_time, order book 150/150 level,
  history_v2), `store_ok: true` (Upstash Redis).
- Tanpa header / secret salah → `/api/tick` dan `/api/admin` menjawab 401.
- Tick uji coba di Vercel memakai namespace `KEY_PREFIX=uas_test` (bukan `uas`), sehingga log forward
  test di namespace `uas` hanya berisi panggilan setelah freeze.

## Log mentah (storage `uas:log:<nama>`, ekspor ke `logs/<nama>.jsonl`)

| Log | Isi per baris |
|---|---|
| `calls` | setiap panggilan: pemicu, waktu mulai/selesai, server_time, candle diproses, telat, status, jumlah request/error |
| `signals` | per candle × pasangan: close, EMA20/50/200, ADX, buy, sell, window_ok, waktu proses |
| `orders` | waktu, pasangan, sisi, qty, best bid/ask, mid, harga fill rata-rata, level terpakai, fee, spread, slippage, harga sinyal, selisih vs sinyal |
| `trades` | round-trip: masuk/keluar, fee, spread, slippage, laba kotor (mid-ke-mid), laba bersih |
| `equity` | ekuitas per panggilan (posisi dinilai di best bid) + best bid/ask BTC untuk benchmark |
| `daily_equity` | ekuitas panggilan pertama setelah 00.00 WIB |
| `errors` | error API (tiap retry) & exception |
| `events` | validasi data, kill switch, daily loss, panggilan duplikat, reject sinyal, catatan perbaikan |
| `snapshots` / `spreads` | order book mentah tiap pasangan per panggilan / ringkasannya |

## hitung_ulang & dashboard offline

```bash
python3 scripts/export_logs.py --url https://<proyek>.vercel.app   # log mentah → logs/
python3 scripts/hitung_ulang.py --fetch                             # → dashboard/dashboard_offline.html + results/hitung_ulang_metrics.json
```

`hitung_ulang` menjalankan ulang backtest dari candle mentah (dan memastikan hasilnya IDENTIK dengan
`results/backtest_summary.json`), menghitung metrik forward dari log mentah, menarik candle jendela
forward dari Indodax, menjalankan ulang backtest pada jendela 10 hari itu dengan modal & state awal
yang sama, lalu membandingkan sinyal candle demi candle dan harga fill per order (delay jadwal,
spread, slippage). Dashboard Vercel memanggil fungsi yang sama (`core/build.py`), jadi angkanya sama.

## Keamanan

- Tidak ada API key Indodax (hanya endpoint publik).
- `CRON_SECRET` dan token storage hanya di env Vercel / `.env` lokal; `.env` ada di `.gitignore`;
  `.env.example` tanpa nilai. Endpoint tick/admin/health fail-closed bila `CRON_SECRET` kosong.

## Pernyataan penggunaan AI

Kode, dokumentasi, dan kerangka refleksi disusun dengan bantuan Claude Code (Anthropic).
Semua angka backtest/forward dihasilkan oleh skrip di repositori ini dari data Indodax asli;
tidak ada angka yang ditulis tangan di dashboard.

## Batasan

- Backtest mengisi order di open candle berikutnya ± biaya terukur; bot mengisi di order book live
  beberapa menit setelah candle tertutup (selisihnya dianalisis di dashboard).
- Snapshot sebelum freeze hanya beberapa hari, sehingga median spread backtest berasal dari sampel pendek.
- Survivorship: lihat `STRATEGI.md` §3.
