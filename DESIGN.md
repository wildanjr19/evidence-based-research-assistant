---
version: alpha
name: "Evidence-Based Research Assistant"
description: "Meja baca literatur ilmiah: klaim, sitasi, dan kutipan sumber."
sourceUrl: "https://blurr.ing/id/"

colors:
  primary: "#0f172a"
  on-primary: "#ffffff"
  background: "#ffffff"
  surface: "#f1f5f9"
  border: "#1f1f1f"
  text: "#0f172a"
  text-muted: "#3d3c38"
  accent: "#64748b"

typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif"
    fontSize: 52px
    fontWeight: 700
    lineHeight: 1.06
    letterSpacing: -2.08px
  heading:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: 22px
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: -0.66px
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.65
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.5

spacing:
  base: 4px
  scale: [4, 8, 12, 16, 20, 24, 32, 44, 84]

radius:
  sm: 1px
  md: 6px
  lg: 11px
  xl: 26px
  pill: 9999px

shadows:
  card: "rgba(23, 23, 21, 0.08) 0px 0px 0px 1px"
  elevated: "rgba(15, 23, 42, 0.08) 0px 0px 0px 1px, rgba(15, 23, 42, 0.08) 0px 2px 4px 0px, rgba(15, 23, 42, 0.45) 0px 28px 60px -20px, rgba(15, 23, 42, 0.4) 0px 60px 120px -50px"

motion:
  duration-fast: 150ms
  duration-base: 300ms
  duration-slow: 1000ms
  easing: "cubic-bezier(0.16, 1, 0.3, 1)"

breakpoints: [640px, 900px, 1024px, 1180px, 1280px]
---

## Scope

File ini **hanya** berisi sistem desain visual untuk UI Streamlit: warna, tipografi, spacing, radius, shadow, motion, breakpoint.

- Arsitektur sistem, skema data, format sitasi, dan protokol evaluasi ada di `ARCHITECTURE.md`.
- Token awal berasal dari `https://blurr.ing/id/`. M7 memetakan palet dan tipografi ke Streamlit; produk tidak memakai nama, copy, atau aset situs referensi.

## Rationale

## Pemetaan M7 (2026-11-19)

Dial: **ENERGY 1 / RHYTHM 2 / MOTION 1**. UI adalah meja baca untuk peneliti yang
memutuskan apakah kutipan mendukung suatu klaim. Form pertanyaan menjadi fokus
awal; setelah memilih jawaban, fokus berpindah ke klaim dan sumbernya.

- Navy `#0f172a` menjaga kontras teks dan menandai aksi utama. Permukaan widget
  memakai `#f1f5f9`; token indigo lama diganti agar kutipan panjang tetap tenang.
- Body 7px dan mono 10px hasil ekstraksi diperbaiki menjadi 16px dan 14px.
  Caption 14px; judul responsif 1,8–3,25rem. Tinggi baris body menjadi 1,65.
- Sans sistem menghindari unduhan font dan menjaga label mudah dipindai. Kutipan
  memakai Georgia lokal untuk membedakan teks paper dari klaim generator.
- Pola identitas: klaim bernomor diikuti sitasi bernomor, halaman, dan kutipan
  yang dapat dibuka. Nomor adalah referensi bukti, bukan dekorasi.
- Lebar baca maksimum 62rem. Urutan satu kolom berlaku pada ponsel, tablet,
  dan desktop; padding mengecil di 640px. Teks panjang membungkus.
- Radius mengikuti widget native; tanpa shadow besar, glass, gradien, logo,
  ilustrasi, atau animasi dekoratif. Fokus keyboard memakai slate `#64748b`.
- Tema terang mendukung pembacaan paper. Toolbar developer disembunyikan dengan
  mode minimal; UI tidak menyediakan toggle tema. Gerak dinonaktifkan ketika
  pengguna memilih reduced motion.

Tema berada di `.streamlit/config.toml`; aturan tipografi dan reflow berada di
`src/rag/ui/style.css`. Pemetaan memakai [konfigurasi tema resmi Streamlit](https://docs.streamlit.io/develop/concepts/configuration/theming).

### Pertanyaan baru melalui API

Form Tanya korpus menambahkan checkbox izin API berbayar yang default-nya mati.
Label memuat batas request per submit; catatan di dekatnya menunjukkan model,
provider, batas output, dan pengiriman pertanyaan/chunk ke provider. Checkbox
native memakai target minimal 44px dan fokus yang sama dengan radio. Caption
setelah submit menunjukkan percobaan, cache hit, serta token tercatat; kegagalan
API dibedakan dari cache miss dan ketiadaan bukti. Dial serta palet tetap 1/2/1.

### Korpus bibliografi S4

Dial tetap **ENERGY 1 / RHYTHM 2 / MOTION 1**. Caption korpus aktif membedakan
referensi terdaftar dari paper terindeks; ekspander memuat judul/citation key
sebagai pemeriksaan cakupan sebelum bertanya. Form tetap menjadi fokus awal.
Pilot bibliografi langsung membuka form, tanpa pilihan demo yang merujuk korpus
lain. Sitasi memuat citation key, judul, dan halaman PDF agar peneliti dapat
mencocokkan bukti dengan daftar pustaka; ID panjang membungkus pada teks biasa.
Section ditandai sebagai perkiraan parser, disertai catatan tentang tabel/rumus.

Heading jawaban memakai h2 setelah h1. Tombol submit diberi selector khusus
untuk mempertahankan target minimal 44px terhadap gaya native Streamlit 40px.
Tidak ada palet, aset, navigasi, atau animasi baru.
