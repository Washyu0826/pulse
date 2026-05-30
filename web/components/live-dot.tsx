/** LIVE 指示燈（純 CSS animate-ping）。 */
export function LiveDot() {
  return (
    <span aria-hidden className="relative flex h-1.5 w-1.5">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-primary opacity-60" />
      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent-primary" />
    </span>
  );
}
