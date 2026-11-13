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
11. **Camera-aware evidence** — include the configured camera name in timeline
   rows, mobile activity cards, and query evidence so multi-camera answers are
   immediately attributable to a source.
12. **Timeline search** — search event type, action, location, person, and
   object/category text with wildcard-safe matching and an explicit web form.
13. **Shareable timeline state** — persist timeline filters in the URL so a
   refresh, browser navigation, or shared link preserves the operator’s view.
14. **Camera health visibility** — record throttled frame heartbeats and safe
   error codes, then show online, starting, stale, error, or paused state.
15. **Provider setup guardrails** — infer matching cloud adapters from device
   URL schemes and reject contradictory explicit protocols before persistence.
16. **Evidence source labels** — show camera context directly in web and mobile
   answer cards alongside matched people, objects, and locations.
17. **Camera setup wizard** — split source naming/type from URL/location entry,
   add provider-specific placeholders, and validate the draft before submit.

## Next high-value improvements

18. **Camera diagnostics** — show last frame, last successful connection,
    reconnect attempts, codec/fps, clock skew, and a clear remediation path.
19. **Evidence-first answer cards** — show the answer, confidence, event time,
    matched person/object labels, camera, and one-click clip preview together.
    Make “not enough evidence” a first-class state.
20. **Timeline grouping and navigation** — group events by hour/location, add
    date presets, keyboard shortcuts, and URL-persisted filters.
21. **Trust and retention controls** — add per-camera retention previews,
    export/delete audit logs, event redaction controls, and an explicit privacy
    status indicator before recording begins.

## Product-level follow-ons

After the above, prioritize saved questions, multi-camera handoff (“follow the
blue bag from the kitchen to the garage”), natural-language time ranges,
operator annotations, and a synthetic camera fixture for repeatable end-to-end
demo/testing flows.
