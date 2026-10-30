# Extractable components

## Layout

## SiteHeader
- Source: `templates/base.html` (header.site-header + div.demo-banner)
- Category: layout
- Description: Amber prototype banner, brand (ship icon + "Ship Booking"), nav: Search, Service updates, Help centre, FAQ, Contact
- Extractable props: activeItem (string, default: "search")
- Hardcoded: labels, ship icon, CSS

## SiteFooter
- Source: `templates/base.html` (footer.site-footer)
- Category: layout
- Description: Navy footer with Travel information, Support, Policies (12 links), Company (not-configured placeholders)
- Extractable props: none
- Hardcoded: all links and text

## Basic

## SearchForm
- Source: `templates/includes/search_form.html`
- Category: basic
- Description: From/To port selects, date, passengers, teal Search sailings button
- Extractable props: none
