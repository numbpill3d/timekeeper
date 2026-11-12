# UX and functionality improvement plan

This plan prioritizes trust, time-to-answer, and operator confidence for a
local camera evidence system.

## Shipped in this pass

1. **Origin-safe API client** — use a relative `/api` base URL by default so
   the UI works through `localhost`, `127.0.0.1`, LAN hostnames, and HTTPS.
2. **WebSocket proxy support** — enable Vite WebSocket proxying and derive the
   socket protocol from the current page instead of hard-coding a host.
3. **Actionable query suggestions** — provide useful example questions when
   the history is empty, so a new operator can discover the product quickly.
4. **Clear query history** — let operators reset a conversation without
   refreshing the page.
5. **Query error recovery** — show an inline, accessible error with the next
   diagnostic step instead of inserting a vague assistant message.
6. **Mobile navigation** — replace the icon-only collapsed sidebar with an
   accessible open/close navigation drawer on small screens.
7. **Mobile query access** — keep the query interface available below the live
   activity feed instead of hiding the core product action on mobile.
8. **Accurate dashboard metrics** — calculate “events today” from a dedicated
   day-scoped request instead of counting only the recent activity window.
9. **Reduced-motion support** — honor `prefers-reduced-motion` and provide
   tactile button feedback without making the interface distracting.
10. **Semantic interaction labels** — add navigation landmarks, button labels,
    form semantics, live query status, and dialog semantics for assistive tech.

## Next high-value improvements

11. **Camera setup wizard** — guide operators through source type, location,
    credentials, connectivity test, retention, and a first-frame preview. Keep
    secrets masked and never echo them in validation errors.
12. **Camera diagnostics** — show last frame, last successful connection,
    reconnect attempts, codec/fps, clock skew, and a clear remediation path.
13. **Evidence-first answer cards** — show the answer, confidence, event time,
    matched person/object labels, camera, and one-click clip preview together.
    Make “not enough evidence” a first-class state.
14. **Timeline grouping and search** — group events by hour/location, add full
    text search, date presets, keyboard shortcuts, and URL-persisted filters.
15. **Trust and retention controls** — add per-camera retention previews,
    export/delete audit logs, event redaction controls, and an explicit privacy
    status indicator before recording begins.

## Product-level follow-ons

After the above, prioritize saved questions, multi-camera handoff (“follow the
blue bag from the kitchen to the garage”), natural-language time ranges,
operator annotations, and a synthetic camera fixture for repeatable end-to-end
demo/testing flows.
