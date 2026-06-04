Vendored UI font assets for local-first rendering.

These files replace runtime Google font/icon stylesheet requests so DeployWhisper
keeps the same dashboard typography and Material icon rendering without requiring
browser internet access.

- Plus Jakarta Sans weights 400, 500, 600, 700, and 800: SIL Open Font License 1.1.
- Material Icons regular: Apache License 2.0.

Keep `ui.theme.LOCAL_DESIGN_ASSET_CSS` in sync when adding, removing, or renaming
font files.
