"""Browser checks with mocked paid operations; run with an existing Playwright install."""

import argparse
import json
import logging
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=dict(width=1280, height=1000))
        page.context.route(
            "https://example.org/**", lambda route: route.fulfill(body="Fixture sumber")
        )
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.get_by_text("2.514", exact=True).wait_for()
        page.screenshot(path=str(args.output / "real-corpus-desktop.png"), full_page=True)
        evidence.append(
            "Runtime corpus ledger read from the real local API; no generation/evaluation."
        )

        claim = dict(
            claim_id="fixture-c1",
            claim_order=1,
            text="Fixture uji UI: klaim ini hanya memeriksa tampilan dan interaksi.",
            citations=["fixture:p1:c01", "fixture:p2:c02"],
            unsupported=False,
        )
        references = [
            dict(
                number=i,
                chunk_id=f"fixture:p{i}:c0{i}",
                paper_id="fixture",
                title="Fixture uji UI, bukan hasil riset",
                page_start=1,
                page_end=2,
                section="Bagian fixture",
                quote="Kutipan fixture uji UI.\nBukan bukti riset.",
                license="LicenseRef-UserProvided-Unverified",
                url="https://example.org/fixture",
            )
            for i in (1, 2)
        ]
        answer = dict(
            answer_id="fixture-answer",
            run_id="fixture-run",
            question="Pertanyaan fixture uji UI?",
            model="fixture-model",
            status="ok",
            claims=[
                claim,
                dict(claim, claim_id="fixture-c2", claim_order=2, citations=[], unsupported=True),
            ],
            references=references,
            verification=[],
            report_path="data/fixture/report.json",
            usage=dict(
                input_tokens=1234,
                output_tokens=80,
                backend_calls=1,
                cache_hits=0,
                unknown_usage_attempts=0,
            ),
        )
        reading = dict(handle="fixture-handle", answer=answer, quality={}, diagnostics=None)
        metadata = dict(
            corpus=dict(
                fingerprint="fixture",
                registered=2,
                indexed=1,
                chunks=12,
                papers=[
                    dict(
                        paper_id="fixture",
                        title="Fixture uji UI, bukan hasil riset",
                        chunks=12,
                        license="LicenseRef-UserProvided-Unverified",
                        license_label="Belum diverifikasi (koleksi PDF lokal)",
                        url=None,
                    ),
                    dict(
                        paper_id="held",
                        title="Fixture parsing ditahan",
                        chunks=0,
                        license="CC0-1.0",
                        license_label="CC0-1.0",
                        url=None,
                    ),
                ],
                citation_keys={"fixture": ["Fixture2026"]},
            ),
            choices=[
                dict(id="0", label="Fixture korpus UI"),
                dict(id="1", label="Fixture pilot UI"),
            ],
            selected="0",
            modes=["bm25", "dense", "hybrid", "hybrid+rerank"],
            default_mode="hybrid",
            demos=[dict(qid="fixture", question=answer["question"], answer_id="fixture-answer")],
            demo_error=None,
            current=None,
            limits=dict(
                generator_calls=2,
                generator_tokens=1024,
                evaluator_calls=5,
                evaluator_tokens=1024,
                model="fixture-model",
                provider="fixture",
            ),
        )
        calls = []
        pending_questions, pending_quality = [], []
        scenario = {
            "answer": "ok",
            "corpus_error": False,
            "empty_demo": False,
            "defer_question": True,
            "defer_quality": True,
            "pdf_error": False,
        }

        def quality_payload(claim_id):
            return dict(
                status="partial" if claim_id == "fixture-c2" else "evaluated",
                scores=dict(
                    faithfulness=None if claim_id == "fixture-c2" else 0.83,
                    response_relevancy=None if claim_id == "fixture-c2" else -0.125,
                ),
                usage=dict(
                    input_tokens=200,
                    output_tokens=30,
                    backend_calls=1,
                    cache_hits=0,
                    unknown_usage_attempts=0,
                ),
            )

        def route_api(route):
            path = route.request.url.split("/api/", 1)[1]
            calls.append(path)
            if path.startswith("corpus"):
                if scenario["corpus_error"]:
                    route.fulfill(
                        status=400,
                        json=dict(error="Fixture: korpus tidak tersedia. Muat ulang korpus."),
                    )
                    return
                payload = dict(metadata, selected="1" if "corpus=1" in path else "0")
                if scenario["empty_demo"]:
                    payload["demos"] = []
                route.fulfill(json=payload)
            elif path in {"question", "demo"}:
                if scenario["defer_question"]:
                    pending_questions.append(route)
                    return
                payload = json.loads(json.dumps(reading))
                if scenario["answer"] != "ok":
                    payload["answer"].update(
                        status=scenario["answer"],
                        claims=[],
                        references=[],
                        retrieved_chunks=[
                            dict(
                                chunk_id="fixture:p1:c01",
                                paper_id="fixture",
                                page_start=1,
                                page_end=1,
                                section=None,
                                text="Bukti hasil pencarian fixture.",
                            )
                        ],
                    )
                route.fulfill(json=payload)
            elif path == "quality":
                if scenario["defer_quality"]:
                    pending_quality.append(route)
                    return
                payload = route.request.post_data_json
                route.fulfill(json=quality_payload(payload["claim_id"]))
            elif path == "diagnostics":
                route.fulfill(
                    json=dict(
                        records=[],
                        labels={
                            "fixture-c1": "Belum diverifikasi",
                            "fixture-c2": "Tidak ada bukti",
                        },
                    )
                )
            elif path.startswith("page"):
                if scenario["pdf_error"]:
                    route.fulfill(status=400, json=dict(error="Fixture PDF tidak tersedia"))
                    return
                route.fulfill(
                    status=200,
                    content_type="image/svg+xml",
                    body=(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="848">'
                        '<rect width="600" height="848" fill="white"/>'
                        '<text x="32" y="64">Fixture halaman PDF uji UI</text></svg>'
                    ),
                )
            elif path.startswith("pdf"):
                if scenario["pdf_error"]:
                    route.fulfill(status=400, json=dict(error="Fixture PDF berubah"))
                    return
                route.fulfill(
                    status=200,
                    content_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="fixture.pdf"'},
                    body=b"%PDF-fixture",
                )
            else:
                route.abort()

        page.route("**/api/**", route_api)
        page.reload()
        page.get_by_text("12", exact=True).wait_for()
        page.get_by_text("Paper dalam korpus aktif", exact=True).click()
        assert page.get_by_text(
            "Belum ada teks yang lolos pemeriksaan kualitas parsing."
        ).is_visible()
        page.get_by_text("Paper dalam korpus aktif", exact=True).click()
        page.get_by_label("Korpus", exact=True).select_option("1")
        page.get_by_text("12", exact=True).wait_for()
        page.get_by_role("button", name="Cari bukti", exact=True).click()
        assert page.get_by_text("Tulis pertanyaan sebelum mencari bukti.").is_visible()
        page.get_by_label("Pertanyaan riset", exact=True).fill("Pertanyaan fixture uji UI?")
        for mode in metadata["modes"]:
            page.get_by_label("Metode retrieval").select_option(mode)
        page.set_viewport_size(dict(width=390, height=1000))
        page.get_by_role("button", name="Cari bukti", exact=True).click()
        page.get_by_text("Mengambil bukti dan menyiapkan jawaban…", exact=True).wait_for()
        assert page.get_by_label("Metode retrieval").is_disabled()
        scenario["defer_question"] = False
        pending_questions[0].fulfill(json=reading)
        page.wait_for_function(
            "document.querySelector('[data-ui=scores] dd')?.textContent === 'Menghitung skor…'"
        )
        before_score = page.locator('[data-ui="claim"]').nth(1).bounding_box()
        page.wait_for_timeout(100)
        assert len(pending_quality) == 2, "Both cards should start before either finishes"
        by_claim = {route.request.post_data_json["claim_id"]: route for route in pending_quality}
        by_claim["fixture-c2"].fulfill(json=quality_payload("fixture-c2"))
        page.locator('[data-ui="claim"]').nth(1).get_by_text(
            "Belum tersedia", exact=True
        ).first.wait_for()
        assert (
            page.locator('[data-ui="claim"]')
            .first.get_by_text("Menghitung skor…", exact=True)
            .first.is_visible()
        )
        assert page.get_by_role("button", name="Cari bukti", exact=True).is_disabled()
        by_claim["fixture-c1"].fulfill(json=quality_payload("fixture-c1"))
        page.get_by_text("0,830", exact=True).wait_for()
        page.wait_for_function("document.querySelectorAll('[data-ui=claim]').length === 2")
        scenario["defer_quality"] = False
        page.get_by_role("button", name="Cari bukti", exact=True).wait_for(state="visible")
        page.wait_for_function("!document.querySelector('button.primary').disabled")
        after_score = page.locator('[data-ui="claim"]').nth(1).bounding_box()
        assert abs(before_score["y"] - after_score["y"]) < 1, (before_score, after_score)
        assert abs(before_score["height"] - after_score["height"]) < 1, (before_score, after_score)
        assert page.get_by_text("-0,125", exact=True).is_visible()
        assert page.get_by_text("Tidak ada bukti untuk klaim ini.").is_visible()
        assert page.get_by_text(
            "Evaluasi belum lengkap. Skor yang gagal tidak dihitung sebagai nol."
        ).is_visible()
        evidence.append(
            "Catalog opens/closes, corpus switches, all four retrieval methods select; "
            "empty submit validates, query renders claims and null/negative scores."
        )
        evidence.append(
            "Two card requests start together; the second completes first without changing "
            "the first card's pending score or re-enabling submit early."
        )
        evidence.append(
            "Loading disables the form; pending-to-completed scores keep card positions "
            "and heights at 390px."
        )
        assert not any(path.startswith("page") for path in calls)
        page.get_by_role("link", name="Sitasi 1:").click()
        assert page.locator("#citation-1").evaluate("node => node.open")
        assert page.locator("#citation-1 > summary").evaluate(
            "node => node === document.activeElement"
        )
        assert not any(path.startswith("page") for path in calls)
        page.locator("#citation-1").get_by_text("Lihat halaman PDF asli", exact=True).click()
        page.locator("#citation-1 img").wait_for()
        page.locator("#citation-1").get_by_label("Halaman PDF", exact=True).select_option("2")
        with page.expect_download() as download:
            page.locator("#citation-1").get_by_role("button", name="Unduh PDF sumber").click()
        assert download.value.suggested_filename == "fixture.pdf", download.value.suggested_filename
        with page.expect_popup() as popup:
            page.locator("#citation-1").get_by_role("link", name="Buka paper sumber").click()
        popup.value.close()
        scenario["pdf_error"] = True
        page.locator("#citation-1").get_by_role("button", name="Unduh PDF sumber").click()
        page.get_by_text(
            "PDF asli tidak tersedia atau identitasnya berubah. Periksa koleksi lokal.", exact=True
        ).wait_for()
        scenario["pdf_error"] = False
        page.locator("#citation-1").get_by_text("Lihat halaman PDF asli", exact=True).click()
        page.get_by_role("link", name="Sitasi 2:").click()
        page.locator("#citation-2 > summary").click()
        for label in ["Pemakaian token", "Tentang skor RAGAS", "Catatan jawaban"]:
            page.get_by_text(label, exact=True).click()
        assert page.get_by_role("table").is_visible()
        page.get_by_text("Diagnostik MiniCheck (opsional)", exact=True).click()
        page.get_by_role("button", name="Jalankan MiniCheck lokal").click()
        assert page.get_by_text("Klaim 1 · Belum diverifikasi", exact=True).is_visible()
        assert calls.count("quality") == 2
        evidence.append(
            "Citation anchors open and focus the matching panel; PDF loads only after "
            "nested details opens; page selector, download, source link, token table, "
            "score notes, run notes and optional MiniCheck work without repeated evaluation."
        )

        for width in (390, 768, 1280):
            page.set_viewport_size(dict(width=width, height=1000))
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                f"overflow at {width}"
            )
            page.screenshot(path=str(args.output / f"claims-{width}.png"), full_page=True)
        page.set_viewport_size(dict(width=1280, height=1000))
        page.evaluate("document.documentElement.style.zoom = '2'")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(args.output / "zoom-200.png"), full_page=True)
        page.evaluate("document.documentElement.style.zoom = ''")
        page.emulate_media(reduced_motion="reduce")
        assert (
            page.locator("button.primary").evaluate(
                "node => getComputedStyle(node).transitionDuration"
            )
            == "0s"
        )
        page.get_by_label("Pertanyaan riset").focus()
        assert (
            page.get_by_label("Pertanyaan riset").evaluate(
                "node => getComputedStyle(node).outlineWidth"
            )
            == "3px"
        )
        page.keyboard.press("Tab")
        assert page.get_by_label("Metode retrieval").evaluate(
            "node => node === document.activeElement"
        )
        page.keyboard.press("Tab")
        page.keyboard.press("Enter")
        page.get_by_text("0,830", exact=True).wait_for()
        evidence.append(
            "Screenshots and overflow assertions pass at 390/768/1280px and 200% zoom; "
            "keyboard Tab/Enter, focus outline and reduced motion checked."
        )
        page.get_by_label("Demo tersimpan", exact=True).check()
        page.get_by_label("Contoh pertanyaan").select_option("fixture-answer")
        page.get_by_role("button", name="Baca jawaban tersimpan").click()
        page.get_by_text("0,830", exact=True).wait_for()
        page.get_by_label("Tanya korpus", exact=True).check()
        for status in ("abstained", "failed"):
            scenario["answer"] = status
            page.get_by_role("button", name="Cari bukti", exact=True).click()
            page.get_by_text("Bukti hasil pencarian", exact=True).wait_for()
            if status == "failed":
                assert page.get_by_text("Generasi jawaban gagal.", exact=False).is_visible()
            else:
                assert page.get_by_text(
                    "Tidak ada bukti yang cukup dalam konteks terambil", exact=False
                ).is_visible()
        scenario["corpus_error"] = True
        page.get_by_label("Korpus", exact=True).select_option("0")
        page.get_by_role("button", name="Muat ulang korpus").wait_for()
        assert page.get_by_role("button", name="Cari bukti", exact=True).is_disabled()
        scenario["corpus_error"] = False
        scenario["empty_demo"] = True
        page.get_by_role("button", name="Muat ulang korpus").click()
        page.get_by_label("Demo tersimpan", exact=True).check()
        assert page.get_by_text("Run demo belum berisi pertanyaan.", exact=False).is_visible()
        evidence.append(
            "Saved demo selection, abstention with retrieved evidence, generation failure, "
            "corpus failure/reload, stale-form disabling and empty demo checked with mock API."
        )
        assert not errors, errors
        evidence.append(
            "No browser page errors. All paid operations mocked; "
            "no real generation, RAGAS or MiniCheck run."
        )
        browser.close()
    (args.output / "browser-check.json").write_text(
        json.dumps(dict(evidence=evidence, calls=calls), indent=2), encoding="utf-8"
    )
    for item in evidence:
        logging.info(item)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
