# UI audit (4 Oct 2026)

A full pass over every screen of the web app, for every persona that can see it, at 1440x900 (full page) and 390x844. Each page was screenshotted, the defects were written down, fixed (in shared components first), and screenshotted again. Real ids used for the parametrised routes: customer `G-JAT7827`, call `CT-3621997`, hardship case `CS-2026-484190`.

## Design rules enforced

| Area | Rule |
|---|---|
| Page header | Every page starts with `SectionTag as="h1"` (2.25rem display face, one-line muted subtitle, actions on the right). The 404 and sign-in pages use it too. |
| Type scale | Four steps only: page title 2.25rem, section title 1.25rem (1.5rem for the public landing sections), card title 1.0625rem, small label 13px body face. Headings are in Neuton, everything else in Poppins. No uppercase or letter-spaced labels. |
| Container | One container for every page: the navbar's `max-w-[1680px]` with `px-5 md:px-10` gutters. No page sets its own narrower width (the sign-in page no longer does). |
| Cards | `Card`: white, 1px warm-grey border, `--radius-lg` (8px), `p-5`. Grey cards only for empty states and assumption notes. No shadows on cards, no gradients, no glows. |
| Tables | `DataTable` for every table: 14px rows, `px-4 py-2.5` cells, an ink rule under a sticky header, numbers right-aligned, tabular and never wrapped, badges never wrapped. Rows scroll inside the table (`min(600px, 68vh)`) with "Show more" in steps of 25; a tail of 10 rows or fewer is shown straight away. |
| Notes | `Footnote` for every source or caveat line under a table (13px muted, 12px above). |
| Buttons | `Button` only: three heights (32, 40, 48), one line, `--radius-md`. One primary (red) action per card; lists of rows use secondary or ghost buttons so a page is not a wall of red. |
| Status | Never colour alone: every status is a `Badge` with an icon and a word (Agrees, Differs, Pass, Fail, Review, Low volume). |
| Tiles | `StatTiles`: 4 per row on desktop, 2 on tablets, 1 on phones, equal heights, numbers in the display face (the same as the home page numbers). |
| Long pages | Aim for at most about 1.5 screens at 1440x900. Pages with several independent parts use `PageTabs` (underlined, state in the URL so links and back work, arrow keys move between tabs); a second level inside a page that already has route tabs uses the segmented variant. Long lists get their own scroll area. |
| Tab labels | A tab label is not repeated as a heading inside the tab; the panel opens with a one-line muted intro instead. |
| Phones | No horizontal page overflow at 390px (checked for every route). Wide tables scroll inside their frame; the queue becomes a stacked list; filter chips scroll sideways in one row; single-column grids use `minmax(0,1fr)` so content cannot push the page wider. |
| Copy | Plain words in tables: codes such as `specialist_referral` or `auto_loan` are shown as words, whole numbers get thousands separators, "n/a" (not a dash) for missing values. |

## Shared components changed

- `SectionTag.tsx`: one heading component for h1, h2 and h3 with the scale above; `large` for landing sections; new `Eyebrow` label.
- `Tabs.tsx`: new `PageTabs` (underline or segmented, URL-backed, keyboard); `RouteTabs` now keeps a tab active for any path under it (the Plan simulator tab was not highlighted on `/hardship/simulator/<case>`); `Segmented` buttons never wrap.
- `DataTable.tsx`: denser rows, scroll area height prop, toolbar `actions` slot, short-tail rule, no wrapping in number cells.
- `Badge.tsx`: never wraps, always in the body face (it was picking up the serif inside headings).
- `StatTiles.tsx`: display-face numbers, equal heights.
- `States.tsx`: quieter empty state, new `Footnote`.
- `FilterBar.tsx`: chips scroll in one row on phones.
- `SqlBlock.tsx`: readable labels on the dark panel (the grey "Semantic layer" label failed contrast), a toast on copy.
- `TranscriptBubbles.tsx`: light two-sided conversation instead of a dark panel; cited turns outlined and labelled "cited".
- `ExplainAccordion.tsx`: the estimate badge drops under the title on phones; the open row uses cream, not pink.
- `index.css`: base heading sizes match the scale.

## Per page

| Page | Found | Fixed |
|---|---|---|
| Signed-out landing | Hero fine (not redesigned). Section headings a different size from the app. | Landing sections use the `large` section size; nothing else changed. |
| /login | 46px title, red icons, narrower container than the navbar. | Standard title size, muted icons, 8px card radius, container aligned with the navbar edges. Height 1.2 to 1.0 screens. |
| /demo | Five red "Start demo" buttons, 1.5rem row titles. | Secondary buttons, section-size titles, muted icons. |
| /demo/:persona (signed out) | Title, text and buttons touching. | Even 12px spacing. |
| /demo/:persona (signed in) | Uppercase serif label, pink "A person decides" box, raw codes in the evidence table. | Sentence-case labels, white note with a red left rule, evidence headers like `DataTable`, codes shown as words, IDs never wrap. |
| Signed-in home (5 personas) | On phones the view switcher wrapped and clipped, four stat rows stacked, buttons different widths. | Switcher scrolls in one line, stats 2x2, full-width buttons on phones. |
| /queue (agent, team lead, specialist) | "Past due" and "Very high" wrapped, rows tall, 2.2 screens; 4.9 screens on phones with a sideways table. | Fixed column widths, no wrapping, a sticky header and its own scroll area, a "Flags" header; a stacked list on phones. 1974 to 1017 px (desktop), 4122 to 2261 px (phone). |
| /customers/:id | Products and history stacked (2.3 screens), header figures overflowed on phones, side panel taller than the screen. | Contact history and Products as tabs, history in its own scroll area, figures fit on phones, side panel scrolls, eligibility icons no longer shrink. 2039 to 1666 px. |
| /calls/:id | 3 screens, transcript on a heavy dark panel, raw approve button, no way back. | Summary on the left (sticky) with labelled fields and the standard button, transcript on the right in a scroll area with cited turns marked, a Back link. 2711 to 1023 px. |
| /ask (agent, team lead, analyst) | Suggestions as a bare list of red links; answers stacked to 1.6 screens with raw column names. | Suggestions as a list card, answers in two columns (table and insight; how it was answered and follow-ups), readable headers and values, icon instead of a warning glyph. |
| /hardship/board, /missed, /overrides | A red "Confirm" on every row; note in a grey card. | Confirm is secondary, "Not hardship" ghost, `Footnote` for the note, links never wrap. |
| /hardship/simulator | Tab not highlighted, no case shown, raw button on the start screen. | Tab highlighted, case and "Change case" above the plan, standard buttons and inputs, empty state, display-face result numbers. |
| /map (team lead, analyst) | 2.9 screens: map, then a 15-row table, then the SQL, then the radar. | Tabs "Weather map" and "Employer radar"; map and top 15 side by side; the query behind a disclosure. 2615 to 1038 px. |
| /team | 3.1 screens of five unrelated sections, page titled "Strategy scorecard". | Page titled "Team" with five tabs (batches first, as in the demo story), counts on the tabs. 2807 to 900 px. |
| /features | Catalog and lookup stacked, a dark custom button. | Tabs "Catalog" and "Live feature vector", standard input and button. 1771 to 1234 px. |
| /governance/quality | Two long tables stacked. | Segmented "Issues found" and "Contract tests". 1936 to 1257 px. |
| /governance/benchmark, /audit | Footnote touching the table. | `Footnote`. |
| /governance/monitoring | A two-column table stretched across the page. | Model first, then text features as a compact three-column list. 1586 to 1205 px. |
| /governance/fairness | Status cut off ("Rev", "Low volum"), raw group names, two long tests stacked. | Badges do not wrap, groups as words, segmented "Outcome test" and "Proxy test". 1957 to 1429 px. |
| /governance/contract | 2.6 screens, a 25-of-27 "Show more", serif badge. | Contract and uses side by side, segmented "Schema" and "Quality rules", whole short tables shown. 2321 to 1460 px. |
| /steward/identity | 2.6 screens of single-column cards, home-made buttons. | Two-column grid of pair cards, standard buttons, six pairs at a time. 2355 to 1209 px. |
| /steward/drift | Uppercase serif labels. | Sentence-case labels, mono table name as the card title. |
| Assistant drawer | Pill-shaped goal chips, uppercase labels, a second sparkle icon in the header. | Chips use the button radius, sentence-case labels, header icon removed, standard secondary "Run". |
| 404 | A grey box with no page header. | Standard page header, empty state and a secondary button back home. |

## Left as is, on purpose

- The landing page is still 2.5 screens: it is the public story page with the globe hero, which was not to be redesigned.
- On phones the customer, fairness and demo-journey pages are 2.5 to 3 screens: everything stacks in one column there; the desktop layouts are within the target.
- The home page map card keeps its own metric switcher under the view switcher; merging the two would change how the map works.
- Rule names in the eligibility list and API-written summary sentences (for example "14064 employers") come from the API and are shown as sent.

## Real-browser pass, 4 Oct 2026

Method: headless Chrome driven over the DevTools protocol against the Docker stack on :8080, signed in with the demo session cookie for each persona. Every screen of every persona (35 routes, including each governance tab, the Fairness NBA view and the hardship simulator) was loaded at 1280, 768 and 390 px. Checks: axe-core (WCAG 2.0/2.1 A and AA plus best practice), a keyboard Tab walk (every stop must show an outline or ring), unlabelled controls, heading order, landmarks, horizontal overflow, tables scrolling inside their own container, and a 40 px tap-target measure at phone width. The Ask and assistant checks used the language-model switch (gpt-6-luna) with a handful of single calls.

### Sources block (Ask and assistant)

| Found | Fixed |
|---|---|
| Table sources repeated their label as the quote, so every table appeared twice. | The quote is dropped when it equals the title. |
| Policy quotes showed raw Markdown (`**kept**`). | Quotes are shown as plain text. |
| In the assistant run, `sql` sources (which carry `ref` and `tables`, not `quote`) showed only a heading, `data` sources and some `document` sources rendered as an empty icon, and call turns read "3510350, turn 13". | SQL shows its text and a "Tables:" line, data sources read "Data product: ...", entries with nothing to show are skipped, call turns read "Call 3510350, turn 13". |
| SQL ran as one clipped line in Sources and in "How I got this". | Both wrap. |
| "How I got this" listed "Data products: sql: ..., table: ..." with internal prefixes, repeating the Sources block. | The line is hidden when Sources has entries, prefixes are stripped otherwise; the whole card is hidden when it would be empty. |
| Policy and note answers showed an empty "Nothing to show" table above the answer. | The table is skipped when the answer is text with sources. |
| Several notes were run together in one paragraph. | One line per note or call. |
| The Sources heading was an h3 straight under the page h1. | `Sources` takes a `level`; Ask uses h2, the drawer keeps h3. |

Checked and fine: policy answer (section plus quote), notes and calls (label, quote, time), generated SQL and tables, in the Ask page for analyst, team lead and agent, and in the assistant drawer for all five personas.

### Accessibility fixes

| Found | Fixed |
|---|---|
| The loading skeleton was a div with `aria-label` and no role (axe aria-prohibited-attr). | `role="status"`. |
| Heading jumps from h1 to h3 on the customer page (recommendation), the simulator (Plan), the map (Highest 15 areas) and Ask (Sources). | Promoted to h2 with the same look. |

Results after the fixes: no axe violations on any screen except one heading-order item on Governance > Fairness (see open items); no screen lacks a visible focus ring; all labelled; one main landmark and one h1 per page; no horizontal overflow at 768 or 390; tables scroll inside their container. Tabs use roving tabindex with arrow keys by design, so only the selected tab is a Tab stop.

### Tap targets (phones, tablets, coarse pointers)

A single block at the end of `styles/index.css` gives buttons, tabs, selects and inputs a 40 px minimum, grows table-cell links and sort headers in height, pads `summary`, gives chip remove buttons an invisible 40 px hit area, and enlarges the map zoom buttons. The menu button and logo link in the header are 40 px. The Customer "Today's queue" and simulator "Change case" links have 40 px height. Desktop sizes are unchanged.

### Open items

- Governance > Fairness has an h1 to h3 jump ("What we found, and what it means") in `Panels.tsx`, which was left alone by request.
- Governance > Fairness > NBA decisions: the tile "Groups flagged 6" does not match "1 in NBA decisions" in the summary tile (the 6 includes by-design groups), and the same "Aggregates only" note appears twice under the table.
- Governance > Monitoring: "Override rate 100.0%" is one override out of one decision, shown as a failure; consider showing the count first or a minimum sample.
- The assistant drawer says "Works with no language model" even when the language-model switch is on.
- Ask caveat text says "Check the SQL below", but the SQL is shown above it.
- The landing "SCROLL" cue and the Leaflet attribution links are below 40 px by design.
