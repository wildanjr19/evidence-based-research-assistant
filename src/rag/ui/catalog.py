DEFAULT_DEMO = "eval/results/2026-11-19T01-25-11Z_7492c6"
LOCAL_UI = "data/skripsi/ui-local/2026-11-21T08-16-45Z_07d296"
LOCAL_RECEIPT = "data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/admission-receipt.json"
CORPORA = {
    "Referensi skripsi lengkap (41 PDF)": (
        "configs/skripsi-local.yaml",
        LOCAL_UI + "/demo",
        LOCAL_RECEIPT,
    ),
    "Pilot skripsi (5 PDF)": (
        "configs/skripsi-pilot.yaml",
        None,
        "data/skripsi/pilot-v1/index/reports/prepare-2026-11-19T07-11-50Z_3aa5f1.json",
    ),
    "Benchmark MVP": (
        "data/m6-multipaper/20261119T004114Z/config-citations-surplus-gpt-authorized-v1.yaml",
        DEFAULT_DEMO,
        None,
    ),
}
