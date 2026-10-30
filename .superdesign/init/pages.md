# Pages

## / (Home)
Entry: templates/pages/home.html
Dependencies:
- templates/base.html
  - templates/includes/icons.html
- templates/includes/search_form.html
- static/css/site.css

## /search/
Entry: templates/pages/search.html
Dependencies:
- templates/base.html
  - templates/includes/icons.html
- templates/includes/search_form.html
- apps/pages/templatetags/site.py (inr, duration filters)
- static/css/site.css

## /sailings/<id>/
Entry: templates/pages/sailing_detail.html
Dependencies:
- templates/base.html
  - templates/includes/icons.html
- apps/pages/templatetags/site.py
- static/css/site.css

## /contact/
Entry: templates/pages/contact.html
Dependencies:
- templates/base.html
- static/css/site.css
