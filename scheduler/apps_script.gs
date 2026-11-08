// Penjadwal tambahan untuk bot UAS — Google Apps Script (time-driven trigger tiap 15 menit).
//
// Kenapa: jadwal GitHub Actions bisa terlambat/terlewat (pada 8 Nov 2026 jadwal GitHub tidak
// berjalan sama sekali antara 15.14–17.36 UTC). Dua penjadwal aman dipakai bersamaan karena bot
// idempoten: candle yang sama hanya diproses sekali, panggilan lain tercatat `already_processed`.
// Setiap panggilan diberi tanda `src=apps-script` sehingga log `calls` menunjukkan penjadwal mana
// yang memproses tiap candle.
//
// Pemasangan (di akun Google sendiri):
//   1. https://script.google.com -> New project -> tempel file ini.
//   2. Project Settings -> Script Properties:
//        TICK_URL    = https://uas-algo-trading-indodax.vercel.app/api/tick
//        CRON_SECRET = <nilai CRON_SECRET; JANGAN ditulis di kode ini>
//   3. Jalankan install() sekali (izinkan akses), lalu tick() sekali dan cek Executions.
// Kuota akun gratis: ~90 menit runtime trigger/hari dan 20.000 UrlFetch/hari; pemakaian ini
// ~96 panggilan/hari (24 x ~30 detik + 72 x ~1 detik).

function tick() {
  const p = PropertiesService.getScriptProperties();
  const url = p.getProperty('TICK_URL');
  const secret = p.getProperty('CRON_SECRET');
  if (!url || !secret) throw new Error('Script Properties TICK_URL / CRON_SECRET belum diisi');
  const res = UrlFetchApp.fetch(url + '?src=apps-script', {
    method: 'post',
    headers: { Authorization: 'Bearer ' + secret },
    muteHttpExceptions: true,
  });
  console.log(res.getResponseCode() + ' ' + res.getContentText().slice(0, 300));
}

function install() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('tick').timeBased().everyMinutes(15).create();
}
