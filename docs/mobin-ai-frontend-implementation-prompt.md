# Mobin'AI frontend implementation prompt

Use this document as the build prompt for a **new, independent repository named `mobin-ai-frontend`**. Read the existing website proposal at `docs/mobin-ai-implementation-proposal.md` for product context, but follow this document when the two differ. The decisions in this prompt replace the proposal's link-only website integration and its 10-question-per-day client quota. The frontend must support an embedded popup, and the backend-issued conversation token has a **100 accepted-question lifetime quota**. The backend may enforce additional abuse limits; display those only when the API reports them.

## Mission and ownership

Build a polished, production-ready chat frontend for Mobin'AI, an assistant that answers questions from Mobin Shaterian's technical writing. Deploy the frontend independently at `https://chat.mobinshaterian.com`. It calls the separate `mobin-ai-backend` API at `https://api.mobinshaterian.com`. The existing `mobinshaterian.com` repository should contain only a small integration snippet or loader reference for the chatbot. All chat UI, styles, embed loader, assets, client API code, and frontend tests belong in `mobin-ai-frontend`.

**Frontend scope only.** Do not create FastAPI routes, a database, a RAG pipeline, an AI provider adapter, a local model proxy, an API key holder, or a server endpoint that forwards chat requests. The frontend sends requests directly to the documented Mobin'AI API. A mock API used solely for local development and browser tests is acceptable. Do not copy the knowledge graph or article corpus into the frontend.

Produce working source code, not just a mockup. Include setup, build, test, deployment, and embedding instructions. If the backend repository is not available yet, implement against a versioned contract fixture described below, mark assumptions clearly, and make the API adapter easy to replace with the pinned backend OpenAPI client later. Do not claim an unverified endpoint already exists.

## Product journey

1. A visitor opens the standalone chat page or the popup on `mobinshaterian.com`.
2. Before sending a question, show a short registration form with **given name**, **family name**, and **at least one of email or phone**. Both names are required. Email and phone may both be provided. Do not ask for a password.
3. Show a concise privacy explanation and link to the privacy page. Require an unchecked privacy acceptance box. Show a separate, unchecked optional marketing consent box. Declining marketing must not block chat.
4. Render Cloudflare Turnstile for registration when configured. Obtain its response token immediately before submitting registration data. The backend validates that token. Never expose the Turnstile secret in the frontend.
5. Send the registration to `mobin-ai-backend`. The backend creates or identifies the client and issues a conversation credential through the registration/conversation flow. The credential is scoped to that conversation and permits **100 accepted questions total**. Show the remaining count when the API supplies it.
6. After the token is available, switch to the chat room. The visitor writes a question. Send the question and conversation identifier to the backend with the token. The backend performs RAG and returns or streams the answer.
7. Render the answer as safe Markdown, with citations linking to source articles. Permit follow-up questions in the same conversation until the server reports that the quota is exhausted or the token expires.
8. On refresh, recover the same browser session when the credential is still valid. If recovery fails, show a clear new-session path. Do not imply that the visitor can recover the conversation on a different device; this MVP has no account or contact ownership verification.

The backend is the source of truth for the token, quota, conversation identity, answer, citations, and accepted-request count. Never decrement the displayed quota based only on a button click. Do not turn a failed submission into two charged requests through automatic replay.

## Design and responsive behavior

The visual theme is **black/dark** by default, consistent with the current site's technical portfolio style. Use near-black surfaces, readable off-white text, restrained accent color, visible borders and focus rings, and sufficient contrast. Keep the tone clean and professional. Provide both a compact widget and a comfortable full-page chat view from the same codebase.

The chat window needs a header with Mobin'AI branding, an honest one-line description, close/minimize control in embedded mode, and an accessible status indicator. The transcript needs distinct visitor and assistant messages, source cards, and clear loading/error states. The composer needs a multiline field, send button, keyboard instructions, and a cancel control during streaming. Support long answers, lists, tables, code blocks, links, and citations without horizontal page overflow.

On desktop, the popup is anchored to the lower right, has an unobtrusive launcher, and opens to a useful chat-panel size without covering the entire page. On mobile, the opened widget should occupy the viewport or a safe-area-aware sheet; account for the virtual keyboard, browser chrome, notch/safe areas, and scrolling inside the conversation. Keep the launcher reachable above the phone's bottom UI. Do not make the website itself horizontally scroll.

The initial widget must be lightweight: load the launcher first, defer the full iframe/chat bundle until first open, and avoid loading Turnstile until registration is visible. Opening the chat must preserve the host page's scroll position. When closed, keyboard focus returns to the launcher.

Use English UI text initially. Visitors may submit English or Persian questions; support right-to-left text entry and display where needed. The backend proposal expects answers in English; do not silently translate answers on the frontend.

## Standalone site and embedding

The frontend must expose a standalone application at `https://chat.mobinshaterian.com/` and an embeddable chat page, for example `/embed`. The standalone page can have a short introduction and example questions, but the registration-to-chat flow is the primary task. The embed page renders the same registration and chat components inside a compact shell, with no duplicate business logic.

Implement **both integration choices** in the frontend repository:

1. **Simple iframe option:** document a copy-paste iframe example pointing to `https://chat.mobinshaterian.com/embed`. This is suitable for a page section or a site-owned popup wrapper. Give the iframe a descriptive `title`, suitable permissions, and responsive dimensions. Never put a token, contact value, or question in its URL.
2. **Recommended popup loader:** publish a small versioned JavaScript file such as `https://chat.mobinshaterian.com/embed/v1.js`. It adds a branded bottom-right launcher to an approved host page and creates the iframe only when opened. Provide a documented script-tag usage example and, optionally, an npm/library entry point built from the same loader code. The loader must be framework agnostic so the current TanStack Start site or any plain HTML page can use it. A caller should not need to install React in the host app.

Use the iframe as the isolation boundary for the popup. Host-page CSS and JavaScript must not alter chat styles; chat CSS must not alter the host page. The loader owns only the launcher, iframe container, and minimal host-side accessibility behavior. It never reads or stores the conversation token. The iframe owns registration, chat state, API calls, and session recovery.

Make the loader safe to add once globally: repeated script execution should not create duplicate launchers; provide a clean `destroy`/unmount path for applications with client-side navigation. Allow a small, documented set of public options such as position offset, initial open state, launcher label, and base URL. Validate options. Do not allow arbitrary HTML injection. Give the iframe an explicit origin and restrict `postMessage` handling to that origin and a small versioned set of events, such as `ready`, `open`, `close`, and `resize`. Do not send tokens, names, contact details, questions, or answers over `postMessage`. Avoid dependence on third-party cookies or parent-page DOM access.

Supply a concrete host-site integration snippet for `mobinshaterian.com` and a second example for plain HTML. Describe where the script belongs in the current site's root layout. Do not modify the website repository as part of implementing the frontend repository unless that task is separately requested.

Configure the deployment so `chat.mobinshaterian.com` can be framed by `https://mobinshaterian.com` and `https://www.mobinshaterian.com`, with a restrictive Content Security Policy `frame-ancestors` allowlist. Do not use `X-Frame-Options: DENY` for `/embed`. Deny embedding from unapproved origins if the hosting platform supports path-specific policy. Set an appropriate CSP for the chat application and loader. The backend must allow CORS from the chat origin; the current website does not need direct backend access because its widget uses the chat-origin iframe.

## Suggested frontend stack and repository layout

Use React 19, TypeScript strict mode, Vite, TanStack Router, TanStack Query, Tailwind CSS, accessible UI primitives, React Hook Form with Zod, and a safe Markdown renderer. The existing proposal suggests TanStack Start; a static Vite application is acceptable here because the UI is an API consumer and should deploy to a CDN or separate web server without a Node runtime. If choosing TanStack Start, configure a real static deployment output or clearly document the required Node server. Do not use its server functions to implement backend behavior.

Suggested layout, adjusted as implementation needs require:

```text
mobin-ai-frontend/
├── src/
│   ├── app/                 # router, providers, bootstrap
│   ├── routes/              # standalone, embed, privacy, about
│   ├── features/
│   │   ├── registration/    # form, consent, Turnstile lifecycle
│   │   └── chat/            # session, transcript, composer, citations
│   ├── components/          # reusable presentational UI
│   ├── lib/api/             # pinned contract, generated types, API adapter
│   ├── lib/session/         # browser-only token handling
│   ├── styles/              # dark theme and responsive layouts
│   └── embed/               # framework-agnostic loader entry point
├── public/
├── contracts/              # pinned OpenAPI artifact or documented fixture
├── tests/                  # unit, contract, and browser tests
├── .env.example
├── package.json
└── README.md
```

Use current stable compatible package versions when implementing, pin a lockfile, and keep the install/build/test commands reproducible. The frontend repository must build and deploy independently of the website and backend source trees.

## Backend API contract to consume

The existing proposal defines these *proposed* `/api/v1` operations. Use a pinned `openapi.json` from `mobin-ai-backend` once it exists. Until then, implement a typed adapter and contract fixture for the intended flow. Keep API paths in one place, not scattered through components.

| Operation | Intended use |
| --- | --- |
| `POST /api/v1/clients` | Submit name, contacts, privacy consent, marketing choice, and Turnstile token; receive `client_id`. |
| `POST /api/v1/conversations` | Create a conversation for that client; receive conversation ID, scoped access token, expiry, and 100-question quota metadata. |
| `GET /api/v1/conversations/{id}` | Validate or reload the current conversation and authoritative quota state. |
| `GET /api/v1/conversations/{id}/messages` | Reload authorized message history after refresh. |
| `POST /api/v1/conversations/{id}/messages` | Submit a question and receive a complete answer when streaming is unavailable. |
| `POST /api/v1/conversations/{id}/messages:stream` | Submit a question and receive typed SSE events when streaming is supported. |
| `POST /api/v1/messages/{id}/feedback` | Send helpful/not-helpful feedback after an answer. |

The user-facing registration form has separate `given_name` and `family_name`. The earlier proposal uses a single `name` field. If the backend contract still has only `name`, join the trimmed parts into `name` in the API adapter while retaining separate form fields. Document this mapping. Do not invent extra backend fields in a production request if OpenAPI does not define them.

The earlier proposal places the scoped token in a secure HTTP-only cookie, while this prompt requires the backend to **return a token that the frontend uses**. Agree the final credential transport with the backend contract before production. This frontend prompt uses an **opaque scoped bearer token returned by `POST /conversations`** as the working contract. Send it only in the `Authorization: Bearer ...` header to `api.mobinshaterian.com` over HTTPS. Do not put it in URLs, analytics, errors, logs, `postMessage`, or host-page state. Keep it in memory and, if refresh recovery is required, in `sessionStorage` scoped to `chat.mobinshaterian.com`; clear it on logout/new session, expiry, and unauthorized responses. Avoid `localStorage` and persistent cookies readable by JavaScript. If the final backend instead requires an HTTP-only cookie, change only the API/session adapter and configure credentialed requests and CSRF protection; do not implement two contradictory credential modes at once.

Recommend this **contract shape** to the backend team; treat the pinned OpenAPI file as authoritative when available:

```json
{
  "client_id": "uuid",
  "conversation_id": "uuid",
  "access_token": "opaque-token",
  "expires_at": "2026-10-25T12:00:00Z",
  "quota": {
    "limit": 100,
    "used": 0,
    "remaining": 100
  }
}
```

The two-step API may return `client_id` from `/clients` and the remaining fields from `/conversations`. Do not assume registration by itself grants chat access. The backend must define whether a new conversation gets a new 100-question quota, whether the same contact can receive more tokens, and when tokens expire. The frontend must not use a registration retry to obtain extra quota. Follow the server's actual `quota` and error responses instead of deriving policy from contact data.

For a question, send a stable idempotency key generated once per intentional submission if the backend supports it. Keep that key across an explicit retry of the same request. Do not automatically resend after an ambiguous network failure unless the backend confirms idempotent handling. Treat a request as quota-consuming only when the API accepts it; update the displayed quota from the response or a follow-up conversation fetch. Disable additional sends while a submission is pending unless the API explicitly supports concurrent requests in one conversation.

For a successful answer, expect an answer body, `message_id`, `conversation_id`, `grounded`, and a `citations` array with stable citation IDs, titles, canonical URLs, and optional snippets. Show a calm insufficient-evidence state when `grounded` is false or the API reports no supporting sources. Display source cards separately from the Markdown body. If a citation ID appears in Markdown, link or highlight it only when it matches a citation returned by the API.

For streaming, parse typed `retrieving`, `citation`, `delta`, `complete`, and `error` events from a **POST** response body. Standard browser `EventSource` only performs GET and does not support bearer headers; use `fetch` with a readable stream and an SSE parser. Support `AbortController` cancellation. Consider the assistant message final only after `complete`. After interrupted or ambiguous streams, re-fetch messages/conversation state before deciding whether to retry. Provide the non-streaming endpoint as a documented fallback if the backend has not released streaming yet.

Map structured API errors (`code`, `message`, `request_id`, optional safe `details`) to friendly, actionable UI states. Include registration validation, expired Turnstile, expired or invalid token, quota exhausted, rate limited, offline, timeout, backend unavailable, and generation failure. Respect `Retry-After` when supplied. Do not render internal error details or stack traces. Show the request ID only as a support reference.

## Registration and privacy details

- Validate given and family names with useful messages; trim whitespace. Require both. Do not reject legitimate international names merely because they contain spaces, apostrophes, or non-Latin letters.
- Require at least one of a syntactically valid email or a phone number. Provide a country-code hint for phones and let the backend perform authoritative normalization. Do not present email/phone as verified identities.
- Link to a real privacy page hosted by this frontend. Explain the collection of name, contact, questions, and chat answers; service follow-up; optional marketing; 12-month retention as planned in the proposal; and a contact route for access/deletion requests. Use text approved by the site owner before launch.
- Keep marketing consent separate and off by default. Record the chosen privacy policy version in the registration payload if the backend contract supports it.
- Render Turnstile with the public site key, action `client_register`, and documented callbacks. Disable submission until verification is ready. Reset after an expired or rejected token. Avoid loading Turnstile in the host website; it belongs inside the chat iframe/application.
- Do not retain the form's email or phone in browser storage after successful registration. Do not send contact information to analytics.
- Use explicit submission status and prevent duplicate form submission while the API call is pending. On safe validation failure, keep entered fields and show the field-level issue.

## Chat room behavior

Show an empty state with a few relevant example questions about Mobin's articles, but label them as suggestions, not precomputed answers. Clicking one fills the composer; it should not send automatically. Display the remaining question quota when reported by the API, for example “87 of 100 questions remaining.” At zero, disable the composer and explain that the token's question limit is reached. If the backend also reports a daily or IP rate limit, show its retry time separately from the lifetime token quota.

Submit on Enter and insert a newline with Shift+Enter, or provide an equally clear keyboard model. Do not submit an empty or whitespace-only question. Show a reasonable character counter based on the API's documented limit. Announce submission and completion through an accessible live region without reading every streaming token aloud. Allow copy-answer and copy-question controls that work on desktop and touch devices. Give each answer a lightweight helpful/not-helpful control if the feedback endpoint exists.

During generation, show a pending assistant message with “Finding relevant articles” and “Writing an answer” states where supported. Keep the transcript scrolled to the latest content only when the visitor is already near the bottom; otherwise show a “Jump to latest” control. Cancel should stop the browser request and then reconcile the server state. Prevent duplicate message bubbles when a stream reconnects or a retry returns the already-created answer.

On refresh, validate the stored session and load the authorized conversation history. If the token is expired, remove local session material and present registration again with a concise explanation. Do not show another visitor's conversation merely because an ID was found in a URL or browser storage. The backend must authorize every history and message request.

## Markdown and citations

The answer format includes headings, paragraphs, bold text, numbered and unordered lists, nested lists, inline code, fenced code blocks, blockquotes, tables, and links. For example, this response should render correctly:

```md
### Recommended high-TPS pipeline

1. **Edge / security layer**
   - Put a **Web Application Firewall** in front of the public path.
   - Use **parameterized queries** and protect trusted internal flows.
   - Add rate limiting, idempotency keys, and request authentication.

2. **Data path**
   - Stream events through Kafka and write bounded batches to ClickHouse. [c1]

| Stage | Purpose |
| --- | --- |
| Kafka | Buffer traffic |
| ClickHouse | Store analytical events |
```

Use a Markdown library with GitHub-flavored Markdown support. Disable raw HTML or sanitize it strictly. Permit only safe URL schemes (`https:`, `http:`, and carefully handled relative links); block `javascript:` and data URLs. External links open safely with `rel="noopener noreferrer"`. Provide an accessible copy button for code blocks and horizontal scrolling **inside** large code/table blocks. Preserve list nesting and visible heading hierarchy in narrow layouts. Markdown rendering must be tested with hostile HTML and malformed links.

Show citation cards in the order of first reference in the answer, then any additional backend citations. A citation card includes title, optional short snippet, and a canonical article link. Validate URLs before rendering. Never infer sources by searching the website in the browser. If citations are absent, avoid implying that an answer is sourced.

## Accessibility and quality

Meet WCAG 2.2 AA where practical. Use semantic form labels, helpful errors, visible focus, correct dialog semantics for the widget, focus trapping only while the popup is open, Escape to close the popup, focus restoration, reduced-motion support, sufficient touch targets, and high contrast in the dark theme. The iframe needs a meaningful title. Support keyboard-only use from launcher through registration, transcript, sources, and composer. Test screen-reader announcements and mobile keyboard behavior.

Keep client/server state explicit: `unregistered`, `registering`, `session-ready`, `loading-history`, `sending`, `streaming`, `rate-limited`, `quota-exhausted`, and `session-expired` are useful states. Avoid scattered booleans that allow contradictory UI. Validate API responses at the boundary so a malformed response produces a safe error rather than a broken chat screen.

Show a friendly offline state and recover when connectivity returns. Do not cache personal contact fields or transcripts with a service worker unless a separate privacy decision authorizes it. Avoid verbose client-side logging of questions and answers. Keep analytics events coarse, such as widget opened, registration completed, and answer completed; never send names, contact values, token, full question, or full answer.

## Configuration and deployment

Document environment variables with safe placeholders in `.env.example`:

```dotenv
VITE_API_BASE_URL=https://api.mobinshaterian.com
VITE_TURNSTILE_SITE_KEY=replace-with-public-site-key
VITE_CHAT_PUBLIC_URL=https://chat.mobinshaterian.com
```

Only public configuration belongs in `VITE_` variables. No AI provider key, backend admin key, Turnstile secret, or database credential may appear in the frontend build. Use HTTPS for all production requests. Document DNS and TLS for `chat.mobinshaterian.com`, static hosting/CDN or a separate web server, fallback routing for client-side routes, cache headers for versioned loader assets, and safe rollback to the previous frontend build.

Coordinate these infrastructure settings with the backend/deployment owner: backend CORS allows `https://chat.mobinshaterian.com` and local development origins; API authorizes bearer tokens on every scoped request; the chat host allows framing only by approved website origins; CSP permits the API and Turnstile resources; no production key is included in the browser. The main website's CSP, if present, must allow the chat iframe and loader script. These are configuration requirements, not permission to implement backend logic in this repository.

The loader URL should be versioned (`/embed/v1.js`) so the existing website can pin it and upgrades can be rolled out independently. Avoid breaking the loader's public API within the same major version. The iframe route may deploy alongside it. Document how to run local embedding tests with two local origins that approximate the production host and chat domains.

## Required tests and verification

Create meaningful tests for the following behavior, using a mock server/contract fixture instead of a real model:

1. Form requires both names and at least one contact method; marketing remains optional and unchecked.
2. Turnstile success, expiry, failure, reset, and duplicate-submit prevention.
3. Successful registration followed by conversation creation and token-bearing chat call.
4. Token/session recovery on refresh, expiry, invalid-token cleanup, and isolation from the host page.
5. Quota rendering from API data, the 100-question limit, quota exhaustion, and separate rate-limit messaging.
6. Non-streamed answer and streamed `retrieving`/`citation`/`delta`/`complete` event handling.
7. An interrupted stream, retry with the same idempotency key when supported, and no duplicate answer bubble.
8. Safe Markdown rendering for nested lists, tables, code, links, raw HTML, and hostile URLs.
9. Citation links, missing citations, and insufficient-evidence answers.
10. Popup open/close, Escape, focus return, duplicate loader initialization, and destroy/unmount.
11. Mobile viewport and keyboard layout, desktop popup size, and full-page chat layout.
12. Browser tests for the full registration-to-answer path, keyboard access, and a parent website loading the versioned embed script.

Run lint, TypeScript checks, unit tests, browser tests, and production builds in CI. Verify generated API types against the pinned OpenAPI artifact once the backend publishes it. A mock backend must be clearly identified as a test fixture and excluded from production deployment.

## Deliverables and acceptance criteria

Deliver a standalone `mobin-ai-frontend` repository containing the application, embedded popup loader, iframe route, pinned API contract or marked provisional fixture, tests, `.env.example`, and a README with exact local and production commands. Provide copy-paste integration examples for the current website and plain HTML. Include screenshots or short recordings of desktop and mobile states in the project documentation if the implementation environment supports them.

The implementation is complete when a visitor can open the popup on `mobinshaterian.com` or visit `chat.mobinshaterian.com`, register with given name, family name, and email or phone, receive a scoped backend token, ask a question, see a RAG answer rendered as safe Markdown with citations, and continue until the backend reports the 100-question quota exhausted. The same flow must work on mobile and desktop. The main website must contain no chat business logic or backend secret, and the frontend must remain independently deployable and replaceable.

Before coding, record any final API contract decisions that the backend must confirm: token transport and expiry, whether quota is per token or per client, whether new conversations can replenish quota, Turnstile fields, exact request/response schemas, idempotency support, and streaming event schemas. Keep these as explicit integration assumptions if backend work is still pending. Continue implementing all frontend work that does not depend on those answers; do not create a substitute backend inside this repository.
