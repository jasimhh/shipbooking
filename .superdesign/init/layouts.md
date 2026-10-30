# Layouts

`templates/base.html` is the single app shell: demo banner, header with brand + nav, messages, `{% block content %}`, footer with four link columns (travel info, support, 12 policy links, company details).

### `templates/base.html`

```html
{% load static %}{% with url_name=request.resolver_match.url_name %}<!doctype html>
<html lang="en-IN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Ship Booking{% endblock %}</title>
  <meta name="description" content="{% block description %}Search and book ship and ferry journeys in India. Prices in INR.{% endblock %}">
  <link rel="canonical" href="{{ request.build_absolute_uri }}">
  <meta property="og:site_name" content="Ship Booking">
  <meta property="og:title" content="{% block og_title %}Ship Booking{% endblock %}">
  <meta property="og:type" content="website">
  {% block robots %}{% endblock %}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  {# ponytail: Google-hosted font; self-host Inter in Phase 9 so no visitor IP goes to a third party. #}
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
  <link rel="stylesheet" href="{% static 'css/site.css' %}">
</head>
<body>
  {% include "includes/icons.html" %}
  <a class="skip-link" href="#main">Skip to main content</a>

  <div class="demo-banner" role="note">
    <div class="container">Prototype: all sailings shown are fictional demo data. Nothing can be booked or paid for yet.</div>
  </div>

  <header class="site-header">
    <div class="container">
      <a class="brand" href="{% url 'pages:home' %}"><svg class="icon" aria-hidden="true"><use href="#i-ship"/></svg>Ship Booking</a>
      <nav class="site-nav" aria-label="Main">
        <ul>
          <li><a href="{% url 'pages:home' %}"{% if url_name == "home" or url_name == "search" %} aria-current="page"{% endif %}>Search</a></li>
          <li><a href="{% url 'pages:service_updates' %}"{% if url_name == "service_updates" %} aria-current="page"{% endif %}>Service updates</a></li>
          <li><a href="{% url 'pages:help' %}"{% if url_name == "help" or url_name == "guide" %} aria-current="page"{% endif %}>Help centre</a></li>
          <li><a href="{% url 'pages:faq' %}"{% if url_name == "faq" %} aria-current="page"{% endif %}>FAQ</a></li>
          <li><a href="{% url 'pages:contact' %}"{% if url_name == "contact" %} aria-current="page"{% endif %}>Contact</a></li>
        </ul>
      </nav>
    </div>
  </header>

  <main id="main" tabindex="-1">
    {% if messages %}
      <div class="container" style="padding-top:24px" role="status">
        {% for message in messages %}
          <div class="alert alert-{% if message.tags == 'error' %}error{% elif message.tags == 'success' %}success{% else %}info{% endif %}">
            <svg class="icon" aria-hidden="true"><use href="#i-{% if message.tags == 'success' %}check{% elif message.tags == 'error' %}alert{% else %}info{% endif %}"/></svg>
            <p>{{ message }}</p>
          </div>
        {% endfor %}
      </div>
    {% endif %}
    {% block content %}{% endblock %}
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div>
          <h2>Travel information</h2>
          <ul>
            <li><a href="{% url 'pages:guide' 'booking-guide' %}">How to book</a></li>
            <li><a href="{% url 'pages:guide' 'boarding' %}">Boarding instructions</a></li>
            <li><a href="{% url 'pages:guide' 'passenger-guidelines' %}">Passenger guidelines</a></li>
            <li><a href="{% url 'pages:guide' 'luggage' %}">Luggage rules</a></li>
            <li><a href="{% url 'pages:guide' 'travel-requirements' %}">Travel requirements</a></li>
            <li><a href="{% url 'pages:guide' 'safety' %}">Safety information</a></li>
          </ul>
        </div>
        <div>
          <h2>Support</h2>
          <ul>
            <li><a href="{% url 'pages:help' %}">Help centre</a></li>
            <li><a href="{% url 'pages:faq' %}">FAQ</a></li>
            <li><a href="{% url 'pages:contact' %}">Contact us</a></li>
            <li><a href="{% url 'pages:service_updates' %}">Service updates</a></li>
            <li><a href="{% url 'pages:policy' 'grievance' %}">Grievance redressal</a></li>
            <li><a href="{% url 'pages:about' %}">About Ship Booking</a></li>
          </ul>
        </div>
        <div>
          <h2>Policies</h2>
          <ul>
            {% for value, label in policy_types %}
              <li><a href="{% url 'pages:policy' value %}">{{ label }}</a></li>
            {% endfor %}
          </ul>
        </div>
        <div>
          <h2>Company</h2>
          <ul>
            <li>{% if business.legal_entity_name %}{{ business.legal_entity_name }}{% else %}<span class="not-configured">Legal entity: not yet configured</span>{% endif %}</li>
            <li>{% if business.registered_address %}{{ business.registered_address }}{% else %}<span class="not-configured">Registered address: not yet configured</span>{% endif %}</li>
            <li>{% if platform_role_label %}Ship Booking acts as {{ platform_role_label }}.{% else %}<span class="not-configured">Platform role: not yet configured</span>{% endif %}</li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">Ship Booking · Prices in Indian rupees (INR)</div>
    </div>
  </footer>
</body>
</html>{% endwith %}

```

