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
16. **Provider setup guardrails** — infer matching cloud and direct-feed
    adapters from source URL schemes and reject contradictory explicit
    protocols before persistence, including partial source updates.
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
   redaction cleanup. Timeline search and CSV snapshots include the note.
29. **Synthetic query fixture** — provide a deterministic inactive camera and
   event sequence so the query flow can be demonstrated and regression-tested
   without physical camera hardware.
30. **Chronological handoff answers** — order multi-event “what happened to”
   and follow-the-item results oldest-first while preserving newest-first
   behavior for latest-event questions.
31. **Handoff source attribution** — preserve source and destination camera
   names on correlated movement evidence so web/mobile answers can verify the
   physical camera path, not only the inferred locations.
32. **Restart-safe handoffs** — restore only the bounded recent pickup window
   from persisted events when the event processor starts, so a short service
   restart does not silently break an otherwise valid camera handoff.
33. **Provider session cleanup** — delete same-host WHEP session resources when
   a cloud stream closes or reconnects, preventing stale provider sessions from
   accumulating while refusing unsafe cross-host cleanup targets.
34. **Ambiguous attribution safety** — refuse to name a person when multiple
   overlapping candidates have near-tied object-association scores, so weak
   evidence becomes unknown rather than a false identity claim.
35. **Possessive item questions** — parse questions such as “what happened to
   John’s blue toolbox?” into separate person and arbitrary item-label filters
   in the local fallback planner.
36. **Multi-camera synthetic handoff** — make the hardware-free fixture use
   deterministic kitchen and garage cameras, and assert that the formatted
   answer preserves pickup, movement, placement, exit, and camera-path facts.
37. **Complete item handoff narratives** — correlate a nearby owner-scoped
    person-exit event with matched pickup/movement/placement evidence so an
    item-history answer can explain both what was taken and who left afterward.
38. **Cross-client live-status clarity** — show on web and mobile whether
    recent activity is receiving live WebSocket events or using the documented
    REST polling fallback, while preserving automatic reconnect behavior.
39. **Actionable query failures** — distinguish quota exhaustion, timeouts,
    and service failures in web/mobile query surfaces so operators know whether
    to wait, narrow the question, or repair the local stack.
40. **Camera-scoped timeline review** — filter timeline evidence by its source
    camera on web and mobile, preserving the existing tenant scope, search,
    bounded since/until time ranges, and event-type filters.

## Next high-value improvements

41. **Policy-level retention controls** — extend the shipped configurable
    per-camera and per-person retention policies with richer policy templates,
    scheduled dry-run reports, and explicit approval workflows before cleanup.
    The shipped baseline already provides web/mobile retention previews, audited
    event redaction, clip cleanup, web/mobile audit history, and web CSV export.

## Product-level follow-ons

After the above, prioritize richer annotation export, additional provider-backed
end-to-end testing, and operational deployment validation with real camera
sessions, token rotation, retention cleanup, and the complete Docker stack.
