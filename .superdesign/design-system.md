# Ship Booking — design system

## Product
Ship Booking is a ship and ferry booking website for India. Prices are in Indian rupees (₹, INR, Indian digit grouping such as ₹1,25,000). Passengers search by departure port, destination, travel date and passenger count; compare sailings by departure/arrival time, duration, fare and availability; open a sailing page; book, pay and receive an e-ticket.

Key pages: Home (search), Search results, Sailing detail, Help centre and guides (booking, boarding, passenger guidelines, luggage, travel requirements, safety), FAQ, Contact, Service updates (delays/cancellations), 12 policy pages.

Current status: prototype. All sailings are fictional demo data on real Indian ports (Mumbai Ferry Wharf, Mandwa Jetty in Alibag, Phoenix Bay Jetty in Sri Vijaya Puram / Port Blair, Swaraj Dweep (Havelock) Jetty). A "Prototype: all sailings shown are fictional demo data" notice and "Demo" badges must stay visible.

## Visual identity: "Midnight harbour" (chosen 2026-10-30; hard constraints)
- Dark theme. Background #07121F, surfaces #0F2133 / #132A40, 1px borders #1E3A52, text #E6EEF5, muted text #8FA3B8.
- Accent: sea-glass #5EEAD4 (primary buttons with dark text #05201C, links, highlights), hover #2DD4BF.
- Status on dark: warning/demo #FCD34D on #1A1607, error #FCA5A5 on #2A0F12, success #86EFAC on #0B2416, info #5EEAD4 on #0B2A2B.
- Fonts: Manrope 600-800 for headings, numbers and buttons; Inter for body and UI.
- 10-12px radius on cards, 8px on buttons and inputs. Never pill-shaped.
- Signature details: faint nautical-chart contour lines in the hero (about 9% opacity), soft sea-glass glow, frosted sticky header, the search form as one segmented bar, large tabular-figure times and prices.
- Lucide-style line icons (stroke 1.8). No emoji.
- Motion: restrained colour transitions only (~150ms); respect reduced motion.
- Source of truth: static/css/site.css.

## Must avoid
Light-theme drift, purple or neon gradients, pill buttons, emoji, heavy animation, cursor effects, fake testimonials or reviews, invented customer counts or ratings, fake partner logos, unsupported claims, generic AI marketing filler, "Made with AI" labels, unlicensed photography.

## Content rules
Plain, factual copy. Don't invent operator names, rules, luggage limits, refund percentages, service alerts or support contacts. Business details that aren't configured yet show as "Not yet configured".

## Accessibility
WCAG 2.2 AA: 4.5:1 text contrast, visible focus ring (sea-glass), labelled form fields, semantic headings, keyboard-usable controls, layouts that work at 375px with no horizontal page scroll.
