# SpecLens design context

A one-page inspection bench: frost page, black stage, safety yellow actions, and a grease pencil for human marks.

## Tokens

- `--sans`: `'Archivo Variable',Arial,sans-serif`, with `font-stretch` up to 125% for headings
- `--hand`: `'Kalam',cursive`, used for anything a person wrote and for marks on the part
- `--frost`: `#dee3e8`
- `--frost-deep`: `#cdd4db`
- `--tag`: `#f8fafb`
- `--ink`: `#17202b`
- `--ink-soft`: `#4b5866`
- `--rule`: `#b9c2cb`
- `--stage`: `#0c0c0d`
- `--marker`: `#ffcf1a`
- `--marker-deep`: `#f2b900`
- `--accept`: `#0b7f56`
- `--reject`: `#cf2a1e`
- `--review`: `#1d5fd1`
- `--pencil`: `#ff5a47`

## Patterns

Stage with a WebGL point cloud of the real photo, pencil ring on the defect, rubber stamp verdict, hover loupe, inspection ticket, part rail, hanging standard tags, paired comparison, and records table. The inspector character reports the current state.

## Constraints

Keep synthetic sample provenance visible. Show empty and connection-error states. Keep credentials on the server. Display observed results without invented counters or accuracy claims. Reduced motion skips the point cloud.
