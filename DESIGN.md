---
version: alpha
name: "Blurr"
description: "Blur bagian mana pun dari halaman web sebelum Anda berbagi layar, live streaming, atau mengambil screenshot. Gambar kotak, klik elemen, atau pilih teks. Gratis."
sourceUrl: "https://blurr.ing/id/"

colors:
  primary: "#0f172a"
  on-primary: "#ffffff"
  background: "#ffffff"
  surface: "#6366f1"
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
    fontSize: 7px
    fontWeight: 500
    lineHeight: 1
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: 10px
    fontWeight: 500
    lineHeight: 1.3

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
- Token di bawah adalah hasil ekstraksi dari `https://blurr.ing/id/` dan belum diterjemahkan ke tema Streamlit. Nilai `typography.body.fontSize: 7px` adalah artefak proses scrape (bukan ukuran teks asli di halaman sumber) — jangan dipakai apa adanya saat memetakan ke `st.set_page_config`/CSS. Perbaiki saat implementasi UI, dan catat perubahannya di file ini.

## Rationale

Measured design tokens extracted from https://blurr.ing/id/. The frontmatter above is the design system — real colors, type scale, spacing, radius, shadows, motion, and breakpoints read from the live page. Upgrade to Pro for the full written system (rationale, component guidance, and accessibility notes).
