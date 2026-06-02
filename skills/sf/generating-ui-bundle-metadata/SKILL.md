---
name: generating-ui-bundle-metadata
description: "MUST activate when the project contains a uiBundles/*/src/ directory and scaffolding a new UI bundle or app, or when editing ui-bundle.json, .uibundle-meta.xml, or CSP trusted site files. Use this skill when scaffolding with sf template generate ui-bundle, configuring ui-bundle.json (routing, headers, outputDir), or registering CSP Trusted Sites. Activate when the task involves files matching *.uibundle-meta.xml, ui-bundle.json, or cspTrustedSites/*.cspTrustedSite-meta.xml."
metadata:
  version: "1.0"
---

# UI Bundle Metadata

## Prerequisites: feature flag

UI Bundles is a **Beta** Salesforce feature (multi-framework). Skills assume the target org has it enabled when `salesforce.features.ui_bundles: true` is set in `.adlc/config.yml`. When the flag is missing or `false`, **do not scaffold** — fall back to the LWC path in [generating-lwc-components](../generating-lwc-components/SKILL.md). A developer flips the flag on once the org's Release Update is acknowledged.

```sh
ui_bundles=$(grep -A1 '^[[:space:]]*features:' .adlc/config.yml 2>/dev/null \
  | grep -E '^\s*ui_bundles:' | awk '{print $2}' | tr -d '"')
[ "${ui_bundles:-false}" = "true" ] || { echo "UI Bundles flag off — refusing to scaffold."; exit 1; }
```

## Scaffolding a New UI Bundle

Use `sf template generate ui-bundle` to create new apps — not create-react-app, Vite, or other generic scaffolds.

**Always pass `--template reactbasic`** to scaffold a React-based bundle.

**UI bundle name (`-n`):** Alphanumerical only — no spaces, hyphens, underscores, or special characters.

### Naming convention: internal vs external

Pick the name based on the audience the spec calls out:

| Audience | Default name | Use when |
|---|---|---|
| Employee / Lightning Experience surface | `ReactInternalApp` (or `<Domain>InternalApp`) | The app runs inside Lightning Experience for internal users |
| Portal / Experience Site / public | `ReactExternalApp` (or `<Domain>ExternalApp`) | The app is served from a Digital Experience Site to external users |

The spec authored by `/spec` should declare which one (see `templates/requirement-template.md` → "Frontend framework"). If the spec is silent, ask once before scaffolding.

**Example:**
```bash
# Internal — employee-facing
sf template generate ui-bundle -n ReactInternalApp --template reactbasic

# External — portal/public-facing
sf template generate ui-bundle -n ReactExternalApp --template reactbasic
```

### Required next step: install npm dependencies

Immediately after `sf template generate ui-bundle`, install dependencies inside the new bundle directory:

```bash
cd uiBundles/ReactInternalApp && npm install
# or
cd uiBundles/ReactExternalApp && npm install
```

Without this step the bundle cannot lint, build, or deploy. Treat scaffolding without `npm install` as an incomplete Phase 1.

After generation:
1. Install npm dependencies (above) — non-negotiable
2. Replace all default boilerplate — "React App", "Vite + React", default `<title>`, placeholder text
3. Populate the home page with real content (landing section, banners, hero, navigation)
4. Update navigation and placeholders (see the `building-ui-bundle-frontend` skill)

## Building and deploying the bundle

Build and deploy use stock sf CLI — there is no UI-Bundle-specific deploy command.

```bash
# Build static assets into uiBundles/<AppName>/dist/
cd uiBundles/ReactInternalApp && npm run build && cd -

# Standard sf deploy
sf project deploy start \
  --source-dir uiBundles/ReactInternalApp \
  --target-org <org-alias>
```

For canary / validate-only flows, swap `start` for `validate`. The directory referenced by `outputDir` in `ui-bundle.json` must exist and be non-empty at deploy time, so always run `npm run build` after any code change before re-deploying.

---

## UIBundle Bundle

A UIBundle bundle lives under `uiBundles/<AppName>/` and must contain:

- `<AppName>.uibundle-meta.xml` — filename must exactly match the folder name
- A build output directory (default: `dist/`) with at least one file

### Meta XML

Required fields: `masterLabel`, `version` (max 20 chars), `isActive` (boolean).
Optional: `description` (max 255 chars).

### ui-bundle.json

Optional file. Allowed top-level keys: `outputDir`, `routing`, `headers`.

**Constraints:**
- Valid UTF-8 JSON, max 100 KB
- Root must be a non-empty object (never `{}`, arrays, or primitives)

**Path safety** (applies to `outputDir` and `routing.fallback`): Reject backslashes, leading `/` or `\`, `..` segments, null/control characters, globs (`*`, `?`, `**`), and `%`. All resolved paths must stay within the bundle.

#### outputDir
Non-empty string referencing a subdirectory (not `.` or `./`). Directory must exist and contain at least one file.

#### routing
If present, must be a non-empty object. Allowed keys: `rewrites`, `redirects`, `fallback`, `trailingSlash`, `fileBasedRouting`.

- **trailingSlash**: `"always"`, `"never"`, or `"auto"`
- **fileBasedRouting**: boolean
- **fallback**: non-empty string satisfying path safety; target file must exist
- **rewrites**: non-empty array of `{ route?, rewrite }` objects — e.g., `{ "route": "/app/:path*", "rewrite": "/index.html" }`
- **redirects**: non-empty array of `{ route?, redirect, statusCode? }` objects — statusCode must be 301, 302, 307, or 308

#### headers
Non-empty array of `{ source, headers: [{ key, value }] }` objects.

**Example:**
```json
{
  "routing": {
    "rewrites": [{ "route": "/app/:path*", "rewrite": "/index.html" }],
    "trailingSlash": "never"
  },
  "headers": [
    {
      "source": "/assets/**",
      "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }]
    }
  ]
}
```

**Never suggest:** `{}` as root, empty `"routing": {}`, empty arrays, `[{}]`, `"outputDir": "."`, `"outputDir": "./"`.

---

## CSP Trusted Sites

Salesforce enforces Content Security Policy headers. Any external domain not registered as a CSP Trusted Site will be blocked (images won't load, API calls fail, fonts missing).

### When to Create

Whenever the app references a new external domain: CDN images, external fonts, third-party APIs, map tiles, iframes, external stylesheets.

### Steps

1. **Identify external domains** — extract the origin (scheme + host) from each external URL in the code
2. **Check existing registrations** — look in `force-app/main/default/cspTrustedSites/`
3. **Map resource type to CSP directive:**

| Resource Type | Directive Field |
|--------------|----------------|
| Images | `isApplicableToImgSrc` |
| API calls (fetch, XHR) | `isApplicableToConnectSrc` |
| Fonts | `isApplicableToFontSrc` |
| Stylesheets | `isApplicableToStyleSrc` |
| Video / audio | `isApplicableToMediaSrc` |
| Iframes | `isApplicableToFrameSrc` |

Always also set `isApplicableToConnectSrc` to `true` for preflight/redirect handling.

4. **Create the metadata file** — follow `implementation/csp-metadata-format.md` for the `.cspTrustedSite-meta.xml` format. Place in `force-app/main/default/cspTrustedSites/`.

