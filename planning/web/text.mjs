// Backend spans count Unicode code points, not JavaScript UTF-16 code units.
export function sourceExcerpt(text, span) {
  return Array.from(text).slice(span[0], span[1]).join('');
}
