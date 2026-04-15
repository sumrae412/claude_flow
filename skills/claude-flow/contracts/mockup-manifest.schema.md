# mockup-manifest.json
<!-- Produced by: Phase 4 (excalidraw-canvas skill) | Consumed by: Phase 5 Step 3d (visual_verify.py --manifest) -->

Path: `docs/design/<feature>/mockup-manifest.json`

## Schema

```json
{
  "feature_slug": "kebab-case-feature",
  "base_url": "http://localhost:3000",
  "screens": [
    {
      "name": "screen-slug",
      "path": "/route/path",
      "states": [
        {
          "name": "default | loading | error | empty | success | <custom>",
          "mockup_file": "docs/design/<feature>/mockups/<screen>__<state>.excalidraw",
          "url_suffix": "",
          "trigger_script": null,
          "wait_for_selector": null
        }
      ]
    }
  ]
}
```

## Field Notes

| Field | Purpose |
|-------|---------|
| `feature_slug` | Must match the directory name under `docs/design/`. Used by consumers that key cached state by feature. |
| `base_url` | Dev-server URL. Playwright navigates to `base_url + path + url_suffix`. Lives in manifest (not per-state) so it's easy to override for CI. |
| `screens[].name` | Kebab-case screen identifier. Matches the `<screen-slug>` in mockup filenames. |
| `screens[].path` | App route. Leading slash. Empty string means the screen lives at `base_url` root. |
| `screens[].states[].name` | Conventional values: `default`, `loading`, `error`, `empty`, `success`. Custom values allowed (e.g. `disabled-for-non-admin`). |
| `screens[].states[].mockup_file` | Path relative to repo root. Must exist when the manifest is emitted. |
| `screens[].states[].url_suffix` | Appended to `base_url + path`. Use for query-string state triggers (`?simulate=error`, `?loading=true`). Default `""`. |
| `screens[].states[].trigger_script` | Optional JS evaluated in the page context before screenshot. Use for states reached by interaction (clicking submit on an empty form to trigger validation). `null` = no script. |
| `screens[].states[].wait_for_selector` | Optional CSS selector to wait for before extracting DOM (e.g., `.error-message` on error state). `null` = rely on `domcontentloaded`. |

## Required States per Screen Type

| Screen type | Required states |
|-------------|-----------------|
| Form screen | `default`, `error` |
| List screen | `default`, `loading`, `empty` |
| List with async loading | `default`, `loading`, `empty`, `error` |
| Mutation screen (create/edit) | `default`, `loading`, `error`, `success` |
| Read-only detail view | `default`, `loading`, `error` |
| Static marketing page | `default` only (note omission in Phase 4 output) |

## Notes

- **Manifest is the gate input.** `visual_verify.py --manifest <path>` iterates every state and fails if any one mismatches the threshold. No happy-path cherry-pick.
- **Manifest is optional for backward compat.** Single-file mode (`visual_verify.py --mockup <file>`) still works for legacy mockups without state matrix.
- **Phase 5 preference order:** if `docs/design/<feature>/mockup-manifest.json` exists, use `--manifest`. Otherwise fall back to `--mockup` single-file mode with the first `.excalidraw` found under `mockups/`.
- **Ties into `defensive-ui-flows` skill:** the required-state matrix mirrors that skill's multi-state-code requirement. Mockup coverage and code coverage should match.
