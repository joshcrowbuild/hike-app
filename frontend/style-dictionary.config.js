// Design token pipeline (DTCG -> CSS custom properties).
// Source of truth: tokens/*.json (W3C Design Tokens format).
// Output: src/design/tokens.css, consumed by the prototype.
// Explicit transform list (no size/rem or time/seconds) so authored
// units pass through unchanged and the render stays identical.
export default {
  source: ['tokens/**/*.json'],
  usesDtcg: true,
  platforms: {
    css: {
      transforms: ['attribute/cti', 'name/kebab', 'color/css', 'fontFamily/css'],
      buildPath: 'src/design/',
      files: [
        {
          destination: 'tokens.css',
          format: 'css/variables',
          options: { outputReferences: true },
        },
      ],
    },
  },
}
