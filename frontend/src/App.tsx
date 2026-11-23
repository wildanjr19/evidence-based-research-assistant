import { useEffect, useId, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from './api.ts';
import { licenseLabel, number, safeSource, score, supportLabel, tokenSummary } from './model.ts';
import type { Bootstrap, Claim, Corpus, Diagnostics, Quality, Reading, Reference } from './types.ts';

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Proses lokal gagal. Periksa koneksi ke server lokal.';
}

function Scores({ result, pending }: { result?: Quality; pending: boolean }) {
  const faithfulness = result?.scores.faithfulness;
  const relevancy = result?.scores.response_relevancy;
  const value = (item: number | null | undefined) => item == null ? pending ? 'Menghitung skor…' : 'Belum tersedia' : score.format(item);
  return <div data-ui="scores">
    <dl className="score-grid">
      <div><dt>Faithfulness</dt><dd>{value(faithfulness)}</dd>
        <div className="score-track" data-empty={faithfulness == null ? '' : undefined} aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(1, faithfulness ?? 0)) * 100}%` }} /></div>
      </div>
      <div><dt>Response Relevancy</dt><dd>{value(relevancy)}</dd></div>
    </dl>
    <p className="micro score-note">{result && ['partial', 'failed'].includes(result.status)
      ? 'Evaluasi belum lengkap. Skor yang gagal tidak dihitung sebagai nol.'
      : 'Skor AI, bukan penilaian manusia.'}</p>
  </div>;
}

function followCitation(event: React.MouseEvent<HTMLAnchorElement>, id: string) {
  const panel = document.getElementById(id);
  if (!(panel instanceof HTMLDetailsElement)) return;
  event.preventDefault();
  panel.open = true;
  panel.scrollIntoView({ block: 'start' });
  panel.querySelector('summary')?.focus({ preventScroll: true });
  history.replaceState(null, '', `#${id}`);
}

function ClaimCard({ claim, references, result, pending }: {
  claim: Claim; references: Map<string, Reference>; result?: Quality; pending: boolean;
}) {
  const citations = claim.citations.map((key) => references.get(key)).filter((ref): ref is Reference => ref !== undefined);
  return <article data-ui="claim" aria-labelledby={`claim-${claim.claim_order}`}>
    <h3 id={`claim-${claim.claim_order}`}>Klaim {number.format(claim.claim_order)}</h3>
    <p className="claim-text">{claim.text}{citations.length > 0 ? <> <span className="citation-mark">[
      {citations.map((ref, index) => <span key={ref.chunk_id}>{index > 0 ? ', ' : ''}<a href={`#citation-${ref.number}`}
        aria-label={`Sitasi ${ref.number}: ${ref.title}`}
        onClick={(event) => followCitation(event, `citation-${ref.number}`)}>{ref.number}</a></span>)}
    ]</span></> : null}</p>
    {claim.unsupported || citations.length !== claim.citations.length || !citations.length
      ? <p className="risk micro">Tidak ada bukti untuk klaim ini.</p> : null}
    <Scores result={result} pending={pending} />
  </article>;
}

function Pdf({ reference, corpus, selected }: { reference: Reference; corpus: Corpus; selected: string }) {
  const pageId = useId();
  const [page, setPage] = useState(reference.page_start);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const params = new URLSearchParams({ corpus: selected, fingerprint: corpus.fingerprint,
    paper: reference.paper_id, page: String(page) });
  async function downloadPdf() {
    setDownloading(true);
    try {
      const response = await fetch(`/api/pdf?${params}`);
      if (!response.ok) throw new Error('PDF tidak tersedia');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] ?? 'source.pdf';
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setFailed(true); }
    finally { setDownloading(false); }
  }
  return <figure data-ui="pdf">
    {reference.page_end > reference.page_start ? <div className="page-control"><label htmlFor={pageId}>Halaman PDF</label>
      <select id={pageId} value={page} onChange={(event) => { setPage(Number(event.target.value)); setLoaded(false); setFailed(false); }}>
        {Array.from({ length: reference.page_end - reference.page_start + 1 }, (_, index) => reference.page_start + index)
          .map((value) => <option key={value} value={value}>{value}</option>)}
      </select></div> : null}
    {failed ? <p className="caption">PDF asli tidak tersedia atau identitasnya berubah. Periksa koleksi lokal.</p>
      : <>
        {!loaded ? <p className="micro" role="status">Memuat halaman PDF asli…</p> : null}
        <div className="pdf-sheet"><img key={page} src={`/api/page?${params}`} width="1240" height="1754"
          alt={`Halaman PDF ${page} dari ${reference.title}`} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} /></div>
      </>}
    <figcaption>Halaman PDF {page} · {reference.title}</figcaption>
    {loaded && !failed ? <button className="secondary download" type="button" disabled={downloading} onClick={() => void downloadPdf()}>
      {downloading ? 'Menyiapkan PDF…' : 'Unduh PDF sumber'}</button> : null}
  </figure>;
}

function Evidence({ reference, corpus, selected, retrieved = false }: {
  reference: Reference; corpus: Corpus; selected: string; retrieved?: boolean;
}) {
  const [showPdf, setShowPdf] = useState(false);
  const keys = corpus.citation_keys[reference.paper_id]?.join(', ');
  const pages = reference.page_start === reference.page_end ? `${reference.page_start}` : `${reference.page_start}–${reference.page_end}`;
  const url = safeSource(reference.url);
  return <details data-ui="evidence" id={`${retrieved ? 'retrieved' : 'citation'}-${reference.number}`}>
    <summary>{retrieved ? `Bukti ${reference.number}` : `[${reference.number}]`} {keys ? `${keys} · ` : ''}{reference.title} · hal. {pages}</summary>
    <div className="details-body">
      <p className="micro">Kutipan asli</p><blockquote data-ui="quote">{reference.quote}</blockquote>
      <code className="chunk-id">{reference.chunk_id}</code>
      {reference.section ? <p className="micro">Section perkiraan parser: {reference.section}</p> : null}
      <p className="micro">Lisensi: {licenseLabel(reference.license)}</p>
      {url ? <a className="button secondary" href={url} target="_blank" rel="noreferrer">Buka paper sumber</a>
        : <p className="micro">Tautan daring belum tersedia; sumber tersimpan sebagai PDF lokal.</p>}
      <details className="pdf-toggle" onToggle={(event) => setShowPdf(event.currentTarget.open)}>
        <summary>Lihat halaman PDF asli</summary>
        {showPdf ? <Pdf reference={reference} corpus={corpus} selected={selected} /> : null}
      </details>
    </div>
  </details>;
}

function TokenUsage({ reading }: { reading: Reading }) {
  const { rows, total, incomplete } = tokenSummary(reading.answer, reading.quality);
  return <details><summary>Pemakaian token</summary><div className="details-body">
    <table><caption className="sr-only">Token API yang tercatat untuk jawaban ini</caption>
      <thead><tr><th scope="col">Tahap</th><th scope="col">Input</th><th scope="col">Output</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.stage}><th scope="row">{row.stage}</th><td>{row.input}</td><td>{row.output}</td></tr>)}</tbody>
    </table>
    <p className="micro">Request API: {number.format(total.backend_calls)} · Cache hit: {number.format(total.cache_hits)}</p>
    <p className="micro">Cache hit tidak menambah token API baru.</p>
    {incomplete ? <p className="micro">Sebagian pemakaian belum diketahui; total hanya menjumlahkan nilai tercatat. Token generator demo tersimpan tidak dihitung sebagai pemakaian baru.</p> : null}
  </div></details>;
}

function AnswerView({ reading, data, evaluating, evaluatePending, diagnose }: {
  reading: Reading; data: Bootstrap; evaluating: boolean; evaluatePending: boolean; diagnose: () => Promise<void>;
}) {
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosticError, setDiagnosticError] = useState('');
  const { answer, quality } = reading;
  const references = new Map(answer.references.map((ref) => [ref.chunk_id, ref]));
  const papers = new Map(data.corpus.papers.map((paper) => [paper.paper_id, paper]));
  const retrieved: Reference[] = (!answer.claims.length || answer.status === 'failed')
    ? (answer.retrieved_chunks ?? []).map((chunk, index) => ({ ...chunk, number: index + 1,
      title: papers.get(chunk.paper_id)?.title ?? chunk.paper_id, quote: chunk.text,
      license: papers.get(chunk.paper_id)?.license ?? '', url: papers.get(chunk.paper_id)?.url ?? null })) : [];
  async function runDiagnostics() {
    setDiagnosing(true); setDiagnosticError('');
    try { await diagnose(); } catch { setDiagnosticError('Diagnostik gagal. Periksa model MiniCheck lokal; jawaban tetap tersedia.'); }
    finally { setDiagnosing(false); }
  }
  return <section className="answer-section" aria-labelledby="answer-heading">
    <div className="answer-head"><h2 id="answer-heading" tabIndex={-1}>Jawaban dan bukti</h2>
      <p className="answer-question">{answer.question}</p>
      <p className="caption">{number.format(answer.claims.length)} klaim · {number.format(answer.references.length)} kutipan sumber
        {evaluating ? ' · Menghitung skor…' : ''}</p></div>
    {answer.status === 'failed' ? <p className="message risk" role="alert">Generasi jawaban gagal. Periksa API key provider di environment atau .env, koneksi, dan laporan run sebelum mencoba lagi.</p> : null}
    {!answer.claims.length && answer.status !== 'failed' ? <p className="message">Tidak ada bukti yang cukup dalam konteks terambil untuk menjawab pertanyaan ini. Coba pertanyaan yang lebih spesifik.</p> : null}
    <div className="claims">{answer.claims.map((claim) => <ClaimCard key={claim.claim_id} claim={claim} references={references}
      result={quality[claim.claim_id]} pending={evaluatePending && !quality[claim.claim_id]} />)}</div>
    {answer.references.length ? <section className="sources" aria-labelledby="sources-heading"><h2 id="sources-heading">Sitasi dan sumber</h2>
      {answer.references.map((ref) => <Evidence key={ref.chunk_id} reference={ref} corpus={data.corpus} selected={data.selected} />)}
      <p className="micro">Nomor halaman mengikuti PDF. Tabel dan rumus dapat kehilangan struktur saat diekstrak; cocokkan angka dengan paper asli.</p>
    </section> : null}
    {retrieved.length ? <section className="sources" aria-labelledby="retrieved-heading"><h2 id="retrieved-heading">Bukti hasil pencarian</h2>
      <p className="caption">Kutipan yang ditemukan; belum menjadi klaim jawaban yang terverifikasi.</p>
      {retrieved.map((ref) => <Evidence key={ref.chunk_id} reference={ref} corpus={data.corpus} selected={data.selected} retrieved />)}
    </section> : null}
    <div className="utilities"><TokenUsage reading={reading} />
      {answer.claims.length ? <>
        <details><summary>Tentang skor RAGAS</summary><div className="details-body caption">
          <p>Faithfulness (0 sampai 1) menilai klaim terhadap seluruh konteks terambil. Response Relevancy (cosine -1 sampai 1) menilai relevansi klaim terhadap pertanyaan; satu klaim belum tentu menjawab seluruh pertanyaan.</p>
          <p>Skor AI bukan jaminan kebenaran atau ketepatan setiap sitasi. Context Recall tersedia pada evaluasi batch dengan jawaban acuan.</p>
          <p className="micro">Evaluasi otomatis, cache-first. Maksimal {data.limits.evaluator_calls} request per klaim, {number.format(data.limits.evaluator_tokens)} output token/request. Pertanyaan, klaim, dan konteks dikirim ke evaluator. Membuka sitasi atau PDF tidak mengulang evaluasi.</p>
        </div></details>
        <details><summary>Diagnostik MiniCheck (opsional)</summary><div className="details-body">
          {answer.claims.map((claim) => { const label = reading.diagnostics?.labels[claim.claim_id] ?? supportLabel(claim, answer.verification);
            return <p key={claim.claim_id} className={`diagnostic-label ${label === 'Didukung MiniCheck' ? 'support' : label === 'Tidak ada bukti' || label === 'Perlu diperiksa' ? 'risk' : ''}`}>
              Klaim {claim.claim_order} · {label}</p>; })}
          {!reading.diagnostics ? <button className="secondary" onClick={runDiagnostics} disabled={diagnosing || evaluating}>
            {diagnosing ? 'Menjalankan diagnostik lokal…' : 'Jalankan MiniCheck lokal'}</button> : null}
          {diagnosticError ? <p className="caption risk" role="alert">{diagnosticError}</p> : null}
          <p className="micro">Keputusan mesin untuk pemeriksaan tambahan; bukan penilaian manusia.</p>
        </div></details>
      </> : null}
      <details><summary>Catatan jawaban</summary><div className="details-body micro">
        <p>Run: <code>{answer.run_id}</code></p><p>Generator: {answer.model ?? 'Belum tersedia'}</p>
        {answer.report_path ? <p>Laporan lokal: <code>{answer.report_path}</code></p> : null}
        {answer.claims.map((claim) => quality[claim.claim_id]?.directory ? <p key={claim.claim_id}>Evaluasi klaim {claim.claim_order}: <code>{quality[claim.claim_id].directory}</code></p> : null)}
      </div></details>
    </div>
  </section>;
}

export function App() {
  const [data, setData] = useState<Bootstrap | null>(null);
  const [selected, setSelected] = useState('0');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [method, setMethod] = useState('hybrid');
  const [source, setSource] = useState('query');
  const [demo, setDemo] = useState('');
  const [reading, setReading] = useState<Reading | null>(null);
  const [phase, setPhase] = useState<'generation' | 'evaluation' | null>(null);
  const active = useRef(0);
  const busy = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    api<Bootstrap>('corpus?corpus=0', undefined, controller.signal).then((result) => {
      setData(result); setReading(result.current); setMethod(result.default_mode);
    }).catch((err: unknown) => { if (!controller.signal.aborted) setError(errorText(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function changeCorpus(value: string) {
    if (busy.current) return;
    const attempt = ++active.current;
    setSelected(value); setLoading(true); setError(''); setReading(null); setDemo(''); setSource('query');
    try {
      const result = await api<Bootstrap>(`corpus?corpus=${encodeURIComponent(value)}`);
      if (active.current === attempt) { setData(result); setReading(result.current); setMethod(result.default_mode); }
    } catch (err) { if (active.current === attempt) setError(errorText(err)); }
    finally { if (active.current === attempt) setLoading(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current || !data || loading) return;
    if (source === 'query' && !question.trim()) { setError('Tulis pertanyaan sebelum mencari bukti.'); return; }
    if (source === 'demo' && !demo) { setError('Pilih contoh pertanyaan dari daftar demo.'); return; }
    busy.current = true; setError(''); setReading(null); setPhase('generation');
    const attempt = ++active.current;
    const context = { corpus: data.selected, fingerprint: data.corpus.fingerprint };
    try {
      const result = await api<Reading>(source === 'query' ? 'question' : 'demo', {
        ...context, request_id: crypto.randomUUID(), question: question.trim(), mode: method, answer_id: demo,
      });
      if (attempt !== active.current) return;
      setReading(result);
      requestAnimationFrame(() => document.getElementById('answer-heading')?.focus());
      if (result.answer.status === 'ok') {
        setPhase('evaluation');
        for (const claim of result.answer.claims) {
          let evaluation: Quality;
          try { evaluation = await api<Quality>('quality', { ...context, handle: result.handle, claim_id: claim.claim_id }); }
          catch { evaluation = { status: 'failed', scores: { faithfulness: null, response_relevancy: null } }; }
          if (attempt !== active.current) return;
          setReading((current) => current?.handle === result.handle
            ? { ...current, quality: { ...current.quality, [claim.claim_id]: evaluation } } : current);
        }
      }
    } catch (err) { if (attempt === active.current) setError(errorText(err)); }
    finally { if (attempt === active.current) { setPhase(null); busy.current = false; } }
  }

  async function diagnose() {
    if (!reading || !data) return;
    const handle = reading.handle;
    const diagnostics = await api<Diagnostics>('diagnostics', { corpus: data.selected, fingerprint: data.corpus.fingerprint, handle });
    setReading((current) => current?.handle === handle ? { ...current, diagnostics } : current);
  }

  const ready = data !== null && data.selected === selected;
  const disabled = loading || phase !== null;
  return <main className="research-app">
    <header className="masthead">
      <h1>Baca klaim.<br />Periksa buktinya.</h1>
      <p className="premise">Evidence-Based Research Assistant · Korpus lokal</p>
      <div className="corpus-control"><label htmlFor="corpus">Korpus</label>
        <select id="corpus" value={selected} disabled={disabled} onChange={(event) => void changeCorpus(event.target.value)}>
          {data ? data.choices.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)
            : <option value="0">Referensi skripsi lengkap</option>}
        </select>
      </div>
      {loading ? <p className="ledger" role="status">Membaca korpus lokal…</p> : data && ready ? <p className="ledger">
        <span><strong>{number.format(data.corpus.papers.length)}</strong> PDF terdaftar</span>
        <span><strong>{number.format(data.corpus.indexed)}</strong> terindeks</span>
        <span><strong>{number.format(data.corpus.chunks)}</strong> chunk</span>
      </p> : null}
      {data && ready && !loading ? <details className="catalog"><summary>Paper dalam korpus aktif</summary><div className="details-body">
        <ul>{data.corpus.papers.map((paper) => <li key={paper.paper_id}>
          <div className="paper-row"><span>{data.corpus.citation_keys[paper.paper_id]?.join(', ')}{data.corpus.citation_keys[paper.paper_id]?.length ? ' · ' : ''}{paper.title}</span>
            <span className="chunk-count">{number.format(paper.chunks)} chunk</span></div>
          <p className="micro">Lisensi: {paper.license_label}</p>
          {!paper.chunks ? <p className="micro">Belum ada teks yang lolos pemeriksaan kualitas parsing.</p> : null}
        </li>)}</ul>
        <p className="micro">Jawaban hanya memakai paper terindeks. Referensi lain belum menjadi sumber bukti.</p>
      </div></details> : null}
    </header>

    <form className={`console${reading ? ' console-quiet' : ''}`} onSubmit={(event) => void submit(event)} aria-label="Pencarian bukti">
      <fieldset disabled={disabled || !ready}>
        <legend>Sumber jawaban</legend><div className="source-options">
          <label><input type="radio" name="source" value="query" checked={source === 'query'} onChange={() => { setSource('query'); setError(''); }} />Tanya korpus</label>
          <label><input type="radio" name="source" value="demo" checked={source === 'demo'} onChange={() => { setSource('demo'); setError(''); }} />Demo tersimpan</label>
        </div>
        {source === 'query' ? <>
          <label htmlFor="question">Pertanyaan riset</label>
          <textarea id="question" value={question} maxLength={8000} onChange={(event) => setQuestion(event.target.value)}
            placeholder="Tulis pertanyaan tentang literatur dalam korpus" aria-describedby="question-help" />
          <p id="question-help" className="micro">Jawaban hanya memakai bukti hasil pencarian dalam korpus aktif.</p>
          <div className="console-actions"><div className="method"><label htmlFor="method">Metode retrieval</label>
            <select id="method" value={method} onChange={(event) => setMethod(event.target.value)}>
              {(data?.modes ?? ['hybrid']).map((mode) => <option key={mode} value={mode}>{mode}</option>)}
            </select><p className="micro">BM25: kata kunci. Dense: kemiripan vektor. Hybrid: gabungan keduanya.</p></div>
            <button className="primary" type="submit">{phase === 'generation' ? 'Mencari bukti…' : 'Cari bukti'}</button>
          </div>
        </> : <>
          <label htmlFor="demo">Contoh pertanyaan</label><select id="demo" value={demo} onChange={(event) => setDemo(event.target.value)}>
            <option value="">Pilih pertanyaan dari evaluasi</option>
            {data?.demos.map((item) => <option value={item.answer_id} key={item.answer_id}>{item.qid} · {item.question}</option>)}
          </select>
          {data?.demo_error ? <p className="caption">{data.demo_error}</p>
            : !data?.demos.length ? <p className="caption">Run demo belum berisi pertanyaan. Pilih korpus lain dari daftar.</p> : null}
          <p className="micro">Jawaban tersimpan; RAGAS otomatis mengevaluasi klaim memakai API jika cache kosong.</p>
          <div className="demo-actions"><button className="primary" type="submit" disabled={!data?.demos.length}>Baca jawaban tersimpan</button></div>
        </>}
      </fieldset>
      {data ? <p className="micro api-note">{source === 'query'
        ? `Generator: ${data.limits.model}. Cache-first; maksimal ${data.limits.generator_calls} request/submit, ${number.format(data.limits.generator_tokens)} output token/request. Pertanyaan dan bukti dikirim ke ${data.limits.provider}. ` : ''}
        Evaluasi otomatis maksimal {data.limits.evaluator_calls} request/klaim, {number.format(data.limits.evaluator_tokens)} output token/request.</p> : null}
    </form>

    {error ? <div className="message" role="alert"><p className="risk">{error}</p>
      {!ready ? <button className="secondary" onClick={() => void changeCorpus(selected)}>Muat ulang korpus</button> : null}</div> : null}
    <div className="activity" role="status" aria-live="polite">{phase === 'generation'
      ? <p>Mengambil bukti dan menyiapkan jawaban…</p>
      : !reading && !loading && !error ? <p>Tulis pertanyaan tentang literatur dalam korpus.</p> : null}</div>
    {reading && data ? <AnswerView key={reading.handle} reading={reading} data={data}
      evaluating={phase === 'evaluation'} evaluatePending={phase === 'evaluation'} diagnose={diagnose} /> : null}
    <footer className="limits"><p>Skor AI bukan jaminan kebenaran atau ketepatan setiap sitasi.</p>
      <p>Cocokkan klaim, kutipan, dan angka dengan paper asli.</p></footer>
  </main>;
}
