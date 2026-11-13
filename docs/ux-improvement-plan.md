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
   object/category text with wildcard-safe matching and explicit web/mobile forms.
13. **Shareable timeline state** — persist timeline filters in the URL so a
   refresh, browser navigation, or shared link preserves the operator’s view.
14. **Camera health visibility** — record throttled frame heartbeats and safe
   error codes, then show online, starting, stale, error, or paused state.
15. **Frame diagnostics** — expose the latest observed resolution and sampled
   FPS next to freshness state without retaining extra image data.
16. **Provider setup guardrails** — infer matching cloud adapters from device
   URL schemes and reject contradictory explicit protocols before persistence.
17. **Evidence source labels** — show camera context directly in web and mobile
   answer cards alongside matched people, objects, and locations.
18. **Camera setup wizard** — split source naming/type from URL/location entry,
   add provider-specific placeholders, and validate the draft before submit.
19. **Timeline quick ranges** — add URL-backed today, 24-hour, and 7-day
   presets so common investigations do not require manual date entry.
20. **Camera diagnostics baseline** — show health state, last frame,
   resolution/FPS, failure count, sanitized error code, and a remediation path.
21. **Evidence-first answer cards** — show answer confidence, event time,
   matched labels, camera, evidence confidence, one-click clip verification,
   and local web/mobile copy actions; make “not enough evidence” a first-class state.
22. **Timeline grouping and navigation** — group consecutive events by local
   hour with counts on web and mobile, add `j`/`k` page shortcuts on web, and
   retain URL-persisted filters plus keyboard/touch clip access.
23. **Timeline CSV snapshot** — export the currently filtered visible page with
   timestamps, sources, labels, confidence, and clip paths for an audit handoff.
24. **Intent-aware local answers** — constrain the no-LLM fallback to an explicit
   pickup, placement, movement, entry, or exit event when the question names
   that action, while preserving open-ended “what happened” searches.
25. **Confidence-aware fallback wording** — qualify low-confidence evidence in
   local answers instead of presenting weak detections with the same certainty
   as strong matches.
26. **Answer-level evidence controls** — carry event identities through the
   query contract so web and mobile answer cards can verify or deliberately
   redact the exact supporting event.
27. **Redaction link cleanup** — remove a redacted event's supporting row and
   any duplicate top-level clip link from the answer card on both clients.
28. **Operator event annotations** — let reviewers add, edit, and clear a
   bounded owner-scoped note beside an event without mutating detector data;
   expose the note on web and mobile timelines and remove it with retention or
   redaction cleanup.

## Next high-value improvements

29. **Trust and retention controls** — add per-camera retention previews,
    export/delete audit logs, event redaction controls, and an explicit privacy
    status indicator before recording begins. Camera cards now surface the local
    configured local default and person-specific override behavior. Individual timeline
    events can be deliberately redacted from web and mobile, with an
    owner-scoped audit record, clip cleanup, and web/mobile audit-history views
    with web CSV export.
    Event redaction controls now ship; broader redaction policies remain follow-on work.

## Product-level follow-ons

After the above, prioritize saved questions, multi-camera handoff (“follow the
blue bag from the kitchen to the garage”), richer annotation search/export, and
a synthetic camera fixture for repeatable end-to-end demo/testing flows.
