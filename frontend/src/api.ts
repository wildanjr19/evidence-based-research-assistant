export async function api<T>(path: string, body?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json', 'X-Requested-With': 'BuktiRiset' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Proses lokal gagal. Muat ulang halaman untuk mencoba lagi.');
  return payload as T;
}
