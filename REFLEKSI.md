REFLEKSI — BACKTEST vs FORWARD TEST
(Draf kerangka. Isi setiap bagian [..] dengan kata-kata sendiri memakai angka dari dashboard /
results/hitung_ulang_metrics.json SETELAH forward test selesai. Jangan menulis angka yang tidak
bisa dihitung ulang dari log.)

1. Ringkasan hasil
   - Backtest 3 tahun: return total, CAGR, MDD, jumlah trade, profit factor. Bandingkan dengan BTC/IDR buy & hold.
     Catatan awal (dari backtest sebelum freeze): laba kotor strategi positif tetapi habis oleh biaya;
     porsi biaya > 100% laba kotor. Fee jual 0,41555% (termasuk pajak 0,21%) adalah komponen terbesar.
   - Forward test 10 hari: [return, MDD, jumlah trade, posisi terbuka di akhir, BTC buy & hold periode sama].

2. Kecocokan sinyal (target 100%)
   - [kecocokan sinyal X/Y candle×pasangan]. Bila < 100%: sebutkan candle mana, dan apakah penyebabnya
     candle yang direvisi Indodax, candle hilang, atau selisih pemanasan indikator (selisih EMA maks relatif = [..]).

3. Selisih harga fill per trade (tabel "Selisih harga fill per order")
   - Keterlambatan jadwal: rata-rata telat [..] menit dari close candle; kontribusi delay [..]%.
   - Spread: spread forward [..]% vs spread backtest [..]% (tabel spread). Kontribusi [..]%.
   - Slippage: [..]%; ukuran order Rp15 juta vs kedalaman buku.
   - Order yang hanya ada di satu sisi (bot vs backtest) dan alasannya (validasi data, kill switch, daily loss, slot).

4. Selisih return forward vs backtest ulang di jendela yang sama
   - Gap return = [..] poin persen. Uraikan: (a) efek harga fill (delay+spread+slippage) × nilai order,
     (b) trade yang berbeda, (c) penilaian posisi terbuka di best bid.

5. Operasional
   - Uptime [..]% ([..]/[..] candle tepat waktu), candle terlambat [..], terlewat [..].
   - Keterlambatan penjadwal GitHub Actions (median/p90/maks) dan dampaknya ke harga fill.
   - Error API [..], kill switch [..], daily loss limit [..], panggilan duplikat yang ditolak [..].
   - Perbaikan bug selama forward test (bila ada) dan bukti bahwa aturan tidak berubah.

6. Spread backtest vs seluruh snapshot
   - Median spread yang dipakai backtest (dari snapshot sampai freeze) vs median seluruh snapshot forward.
     Apakah backtest terlalu optimistis/pesimistis?

7. Pelajaran
   - [mis. pada timeframe 1 jam, biaya transaksi (terutama fee jual + pajak) mendominasi; strategi tren
     butuh pergerakan > ~0,8% pulang-pergi hanya untuk impas; kedisiplinan freeze; pentingnya log.]
