/**
 * `next` yalnızca site içi bir yol olabilir. Aksi halde
 * `?next=https://kotu.site` gibi bir bağlantı, doğrulamadan sonra
 * kullanıcıyı dış bir siteye yönlendirirdi (açık yönlendirme).
 * Döngüyü önlemek için /randevularim, /giris ve /hesabim hedef olamaz.
 */
export function safeNext(next: string | undefined | null): string | null {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return null;
  if (next.startsWith('/randevularim') || next.startsWith('/giris') || next.startsWith('/hesabim')) {
    return null;
  }
  return next;
}
