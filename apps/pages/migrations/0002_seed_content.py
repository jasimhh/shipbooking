"""Starter copy for public pages. Editable afterwards in the admin.

Deliberately general: operator-specific rules (reporting times, luggage
allowances, ID rules) are shown per sailing and must come from the operator.
"""

from django.db import migrations

PAGES = [
    ("about", "about", "About Ship Booking", "What Ship Booking is and what it does.", 0, """
<p>Ship Booking is an online service for searching and booking ship and ferry journeys in India. Prices are shown in Indian rupees (INR).</p>
<h2>Prototype status</h2>
<p>This site is a prototype under development. Sailings currently shown are fictional demonstration data. They cannot be booked, and no real payment is taken.</p>
<h2>How the service works</h2>
<p>Ship Booking lists sailings published by ferry and ship operators. Each sailing page shows the operator, vessel, route, timings, fares and the rules that apply to that journey. The operator runs the voyage and sets its fares, capacity and onboard rules.</p>
"""),
    ("booking-guide", "guide", "How to book", "Step-by-step guide to booking a journey.", 1, """
<ol class="steps">
<li><strong>Search.</strong> Choose your departure port, destination and travel date, and how many people are travelling.</li>
<li><strong>Compare.</strong> Review the available sailings, their departure and arrival times, journey length, fares and remaining availability.</li>
<li><strong>Choose a sailing and class.</strong> Open a sailing to see the vessel, facilities, fare rules and boarding information.</li>
<li><strong>Enter passenger details.</strong> We ask only for the details the journey requires.</li>
<li><strong>Review and pay.</strong> Check the fare breakdown, total in INR and cancellation terms before you pay.</li>
<li><strong>Get your e-ticket.</strong> After payment is confirmed you receive a booking reference and a downloadable e-ticket.</li>
</ol>
<p>Places are held for a limited time while you complete payment. If payment isn't completed in time, the hold is released.</p>
"""),
    ("boarding", "guide", "Boarding instructions", "What to bring and when to arrive at the port.", 2, """
<h2>Before you travel</h2>
<ul>
<li>Check the sailing status on the <a href="/service-updates/">service updates</a> page on the day of travel.</li>
<li>Keep your e-ticket available on your phone or printed.</li>
<li>Carry the identification the operator requires for your route. Requirements are listed on the sailing page.</li>
</ul>
<h2>At the port</h2>
<ul>
<li>Arrive by the reporting time shown on your sailing page and e-ticket. Reporting times are set by each operator.</li>
<li>Port-specific directions, where provided, are shown on the sailing page.</li>
<li>Follow instructions from port staff and crew.</li>
</ul>
"""),
    ("passenger-guidelines", "guide", "Passenger guidelines", "Conduct and responsibilities on board.", 3, """
<ul>
<li>Follow instructions from the crew at all times, including during boarding and disembarking.</li>
<li>Keep children under supervision, especially on open decks.</li>
<li>Do not carry items the operator prohibits. Each operator's onboard rules are listed on the sailing page.</li>
<li>Look after your belongings. Keep valuables and medicines with you.</li>
</ul>
"""),
    ("luggage", "guide", "Luggage rules", "How luggage allowances work.", 4, """
<p>Luggage allowances are set by each operator and can differ by vessel and travel class.</p>
<p>The allowance for your sailing is shown on the sailing page before you pay. If it isn't shown, or you need to carry something unusual such as a bicycle or large equipment, <a href="/contact/">contact support</a> before booking.</p>
"""),
    ("travel-requirements", "guide", "Travel requirements", "Identification and permits you may need.", 5, """
<h2>Identification</h2>
<p>Operators and ports may ask for government-issued photo identification. Requirements for your sailing are listed on the sailing page.</p>
<h2>Permits</h2>
<p>Some island destinations in India require an entry permit, for example Lakshadweep. Permit rules are set by the relevant government authority and can change. Check current requirements with that authority before you book.</p>
"""),
    ("safety", "guide", "Safety information", "Staying safe at sea.", 6, """
<ul>
<li>Pay attention to the safety briefing at the start of the voyage.</li>
<li>Find the life jackets and your nearest assembly point once you are on board.</li>
<li>Do not enter crew-only areas or climb on railings.</li>
<li>Do not carry fuel, gas cylinders, fireworks or other dangerous goods.</li>
<li>In an emergency, follow the crew's instructions.</li>
</ul>
"""),
]

FAQS = [
    ("What currency are prices shown in?", "All prices are in Indian rupees (INR). The fare breakdown, including any taxes and fees, is shown before you pay."),
    ("Can I book right now?", "Not yet. This site is a prototype, and the sailings shown are fictional demonstration data. Booking and payment are being built and will run in test mode first, so no real money is taken."),
    ("How will I receive my ticket?", "After payment is confirmed you will get a booking reference and a downloadable e-ticket. You will also be able to find it in your account."),
    ("Can I cancel a booking?", "Cancellation and refund terms will be published in the Cancellation Policy and Refund Policy before bookings open. The terms that apply to your booking will be shown before you pay."),
    ("How much luggage can I take?", "Luggage allowances are set by each operator. See the luggage rules page and the details on each sailing page."),
    ("What if my sailing is delayed or cancelled?", "Changes to sailings are shown on the service updates page and on the sailing page. Passengers with bookings will also be notified."),
    ("How do I contact support?", "Use the contact form. You will get a reference number to quote in any follow-up."),
]


def seed(apps, schema_editor):
    ContentPage = apps.get_model("pages", "ContentPage")
    FAQ = apps.get_model("pages", "FAQ")
    for slug, section, title, summary, order, body in PAGES:
        ContentPage.objects.get_or_create(
            slug=slug,
            defaults={"section": section, "title": title, "summary": summary, "sort_order": order, "body": body.strip()},
        )
    if not FAQ.objects.exists():
        FAQ.objects.bulk_create(FAQ(question=q, answer=a, sort_order=i) for i, (q, a) in enumerate(FAQS))


class Migration(migrations.Migration):
    dependencies = [("pages", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
