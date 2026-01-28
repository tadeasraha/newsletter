from jinja2 import Template
from datetime import datetime

TEMPLATE = """
<!doctype html>
<html>
<head><meta charset="utf-8"><style>
body{font-family:Arial,Helvetica,sans-serif;color:#111}
.item{border-bottom:1px solid #eee;padding:10px 0}
.prio{font-weight:bold}
</style></head>
<body>
  <h2>Shrnutí newsletterů k {{ date }}</h2>
  {% for item in items %}
  <div class="item">
    <div class="prio">Priorita: {{ item.priority }}</div>
    <h3><a href="{{ item.link }}">{{ item.title }}</a></h3>
    <div>{{ item.summary }}</div>
  </div>
  {% endfor %}
</body>
</html>
"""

def render_digest(items):
    date = datetime.now().strftime("%d/%m/%Y")
    tpl = Template(TEMPLATE)
    return tpl.render(date=date, items=items)
