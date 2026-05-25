/* SolarSTATA wordmark — amber sun mark + sans "olarSTATA" + version chip.
 *
 * The mark is rendered inline (transparent variant of the brand SVG —
 * see desktop/build-resources/mark.svg for the master); the topbar's
 * cocoa background shows through the negative space so the same mark
 * works under both dark and light themes.
 *
 * The version chip pulls from __APP_VERSION__ (injected at build time
 * by vite.config.ts from frontend/package.json) and shortens to the
 * "v{major}.{minor}" form so the chip stays compact AND can never
 * drift out of sync with the actual package version.
 */

const APP_VERSION = (() => {
  // __APP_VERSION__ is injected at build time by Vite's `define`
  // option in vite.config.ts. Vitest's transform pipeline doesn't
  // perform the same substitution, so reading the symbol throws a
  // ReferenceError under jsdom — fall back so the chip renders
  // cleanly in unit tests.
  try {
    return __APP_VERSION__;
  } catch {
    return "0.0.0";
  }
})();

const SHORT_VERSION = (() => {
  const parts = APP_VERSION.split(/[.-]/);
  return `v${parts[0] ?? "?"}.${parts[1] ?? "?"}`;
})();

export function Wordmark() {
  return (
    <div className="flex items-center gap-2 select-none">
      <SunMark size={24} />
      <span className="font-sans text-[15px] font-medium tracking-[0.04em] text-text leading-none">
        solar<span className="italic font-serif text-[19px] text-accent">stata</span>
      </span>
      <span className="font-mono text-[10px] text-text-faint ml-1 px-[6px] py-[2px] border border-border rounded">
        {SHORT_VERSION}
      </span>
    </div>
  );
}

/* Geometry mirrors desktop/build-resources/mark.svg one-to-one. */
function SunMark({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 1024 1024"
      role="img"
      aria-label="SolarSTATA"
      className="shrink-0"
    >
      <g transform="translate(512 512)" fill="var(--accent)">
        {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
          <g key={deg} transform={`rotate(${deg})`}>
            <rect x={240} y={-55} width={160} height={110} rx={55} />
          </g>
        ))}
        <circle cx={0} cy={0} r={190} />
      </g>
    </svg>
  );
}
