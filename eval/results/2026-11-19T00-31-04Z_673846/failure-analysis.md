# Perbedaan dan batas cakupan

Run: `2026-11-19T00:31:04Z_673846`. Catatan di bawah adalah tinjauan AI atas
chunk kanonis setelah hasil terlihat, bukan label manusia baru atau adjudikasi
gold. Semua 52 label manusia tetap utuh. Tidak ada threshold yang disetel dari
sampel ini.

## Lima perbedaan pada batch 1–4

| ID | Manusia | MiniCheck | Chunk | Catatan tinjauan AI |
|---|---|---|---|---|
| `m6-remaining-17` | S | N | `arxiv:2605.14488v1:p8:c12` | Chunk menjelaskan perbandingan versi per metrik dan interaksi. Rincian monitoring sepanjang waktu, drift, dan anomali dalam klaim belum dijelaskan di chunk ini; penyebutan monitoring secara umum tidak melengkapi klausa itu. |
| `m6-remaining-20` | S | N | `arxiv:2605.14488v1:p3:c04` | Chunk membedakan kualitas ranking dengan beberapa tingkat relevansi dari posisi hasil relevan pertama. Ini kandidat negatif keliru MiniCheck menurut pembacaan AI. |
| `m6-remaining-28` | P | N | `arxiv:2605.14488v1:p7:c11` | Chunk mendefinisikan properti; pemakaian breakdown untuk root cause analysis belum dijelaskan. Label P manusia dan N verifier biner tetap kelas berbeda dalam agreement. |
| `m6-remaining-30` | S | N | `arxiv:2605.14488v1:p7:c11` | Tiga properti pada klaim disebut secara eksplisit di chunk. Ini kandidat negatif keliru MiniCheck menurut pembacaan AI. |
| `m6-remaining-31` | S | N | `arxiv:2605.14488v1:p6:c09` | Kebutuhan dataset yang mencerminkan produksi dijelaskan. Anotasi klien yang terikat use case, bagian lain dari klaim, belum dijelaskan di chunk ini. |

Perbedaan tidak otomatis berarti label manusia salah atau verifier benar.
Catatan ini memisahkan kemungkinan dukungan sebagian, batas keluaran biner,
dan kandidat kesalahan verifier. Alasan manusia yang kosong tetap null; catatan
AI tidak dipakai untuk mengisinya. Tidak ada permintaan relabel demi menaikkan
agreement.

## Tujuh input belum terverifikasi

MiniCheck menolak pasangan utuh yang melebihi 512 token tanpa memotong bukti:

- Pilot: `jev-pilot-row-41`, `jev-pilot-row-35`.
- Batch 1: `m6-remaining-03`, `m6-remaining-04`, `m6-remaining-06`.
- Batch 2: `m6-remaining-12`, `m6-remaining-15`.

Coverage seluruh pool 45/52. Pada 40 pasangan batch 1–4, coverage 35/40,
agreement 30/35 (85,7%), Cohen's kappa 0,710265. Lima input yang tidak dinilai
pada batch 1–4 tidak dihitung sebagai cocok ataupun tidak cocok.

Pool berisi satu paper, satu anotator, dan klaim draf referensi AI. Dua belas
pasangan pilot sudah melihat usulan AI; penggabungan deskriptif seluruh pool
(40/45 cocok, kappa 0,767322) bukan pengukuran akurasi independen. Tiga belas
alasan manusia masih kosong. Jumlah 52 memenuhi volume anotasi, tetapi tidak
menyelesaikan korpus lintas paper, gold pertanyaan final, atau benchmark M6.
