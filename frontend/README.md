# Frontend: admin console

React 19 + TypeScript, built with Vite. In development, `/api` is proxied to the
backend on `http://127.0.0.1:8000` (see `vite.config.ts`). In Docker, nginx serves the
build and proxies `/api` (see `nginx.conf`).

## Layout

```text
src/
├── main.tsx                 entry point
├── App.tsx                  shell, navigation and the session-only preview pages
├── Readiness.tsx            System status page (live /api/ready)
├── styles.css               all styles
└── knowledge/
    ├── Connected.tsx        "Stored documents": the page connected to the API
    ├── ExtractionVerification.tsx   side-by-side extraction review and decisions
    ├── Upload.tsx, model.ts preview-only upload flow and browser-side checks
    └── *.test.tsx           Vitest + Testing Library tests, next to the components
```

Only **Stored documents** talks to the backend. The other pages are browser-only
previews whose changes disappear on refresh.

## Commands

```powershell
pnpm install --frozen-lockfile
pnpm dev          # http://localhost:5173 (needs Node 20.19+; Node 24 recommended)
pnpm test         # Vitest
pnpm build        # type-check, then production build into dist/
pnpm exec vite preview --port 5173   # serve dist/ (works on older Node)
```

## Colors

The palette is defined directly in `styles.css`.

| Role | Color |
| --- | --- |
| Primary actions, brand | `#147965` |
| Primary hover | `#0d6554` |
| Focus outline | `#23a28d` |
| Body text | `#243c38` |
| Page background | `#f7f9f8` |
| Borders | `#e0e7e1` |
| Error text | `#a75543` |
| Warning / needs review | `#b4893f` |
| Needs-attention passage border | `#b45309` |
