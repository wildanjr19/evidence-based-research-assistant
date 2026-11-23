export interface Usage {
  input_tokens: number;
  output_tokens: number;
  backend_calls: number;
  cache_hits: number;
  unknown_usage_attempts: number;
}

export interface Paper {
  paper_id: string;
  title: string;
  chunks: number;
  license: string;
  license_label: string;
  url: string | null;
}

export interface Corpus {
  fingerprint: string;
  registered: number | null;
  indexed: number;
  chunks: number;
  papers: Paper[];
  citation_keys: Record<string, string[]>;
}

export interface Claim {
  claim_id: string;
  claim_order: number;
  text: string;
  citations: string[];
  unsupported: boolean;
}

export interface Reference {
  number: number;
  chunk_id: string;
  paper_id: string;
  title: string;
  page_start: number;
  page_end: number;
  section: string | null;
  quote: string;
  license: string;
  url: string | null;
}

export interface Verification {
  claim_id: string;
  chunk_id: string;
  verifier: string;
  label: string | null;
}

export interface Answer {
  answer_id: string;
  run_id: string;
  question: string;
  model: string | null;
  status: string;
  claims: Claim[];
  references: Reference[];
  verification: Verification[];
  report_path?: string;
  usage?: Usage;
  retrieved_chunks?: {
    chunk_id: string;
    paper_id: string;
    page_start: number;
    page_end: number;
    section: string | null;
    text: string;
  }[];
}

export interface Quality {
  status: string;
  scores: { faithfulness: number | null; response_relevancy: number | null };
  usage?: Usage;
  directory?: string;
}

export interface Diagnostics {
  records: Verification[];
  labels: Record<string, string>;
}

export interface Reading {
  handle: string;
  answer: Answer;
  quality: Record<string, Quality>;
  diagnostics: Diagnostics | null;
}

export interface Bootstrap {
  corpus: Corpus;
  choices: { id: string; label: string }[];
  selected: string;
  modes: string[];
  default_mode: string;
  demos: { qid: string; question: string; answer_id: string }[];
  demo_error: string | null;
  current: Reading | null;
  limits: {
    generator_calls: number;
    generator_tokens: number;
    evaluator_calls: number;
    evaluator_tokens: number;
    model: string;
    provider: string;
  };
}
