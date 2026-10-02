/**
 * Yıldız göstergesi.
 *
 * Erişilebilirlik: yıldızlar dekoratiftir (`aria-hidden`), gerçek değer
 * ekran okuyucuya metin olarak verilir ("5 üzerinden 4,6"). Böylece
 * "★★★★☆" karakter çorbası okunmaz.
 *
 * Yarım yıldız `clipPath` yerine iki katman ile çizilir: altta boş
 * yıldızlar, üstte genişliği yüzdeye göre kırpılmış dolu yıldızlar.
 * Bu yaklaşım tek bir SVG tanımıyla her orana çalışır.
 */
export function Stars({
  value,
  size = 'md',
  className = '',
}: {
  value: number;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(5, value));
  const percent = (clamped / 5) * 100;

  const box = size === 'sm' ? 'h-3.5 w-3.5' : size === 'lg' ? 'h-6 w-6' : 'h-4 w-4';
  const gap = size === 'lg' ? 'gap-1' : 'gap-0.5';

  const row = (filled: boolean) => (
    <div className={`flex ${gap}`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <svg
          key={i}
          viewBox="0 0 20 20"
          className={`${box} shrink-0 ${filled ? 'text-brass-500' : 'text-sand-300'}`}
          fill="currentColor"
        >
          <path d="M10 1.6l2.47 5.006 5.526.803-3.998 3.897.944 5.503L10 14.21l-4.942 2.599.944-5.503L2.004 7.41l5.526-.803z" />
        </svg>
      ))}
    </div>
  );

  return (
    <span className={`relative inline-flex ${className}`}>
      <span aria-hidden>{row(false)}</span>
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 overflow-hidden"
        style={{ width: `${percent}%` }}
      >
        {row(true)}
      </span>
      <span className="sr-only">5 üzerinden {clamped.toFixed(1).replace('.', ',')}</span>
    </span>
  );
}
