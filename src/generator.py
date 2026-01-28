"""
Modul pro generování HTML digestu pomocí Jinja2 šablony.
"""
from jinja2 import Template
from datetime import datetime
from typing import List, Dict, Any


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Newsletter Digest - {{ date }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }
        .item {
            margin-bottom: 30px;
            padding: 20px;
            background-color: #fafafa;
            border-left: 4px solid #007bff;
            border-radius: 4px;
        }
        .item.priority-1 {
            border-left-color: #dc3545;
            background-color: #fff5f5;
        }
        .item.priority-2 {
            border-left-color: #ffc107;
            background-color: #fffbf0;
        }
        .item.priority-3 {
            border-left-color: #28a745;
            background-color: #f0fff4;
        }
        .item h2 {
            margin-top: 0;
            color: #007bff;
        }
        .item .source {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 10px;
        }
        .item .priority {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            font-weight: bold;
            margin-right: 10px;
        }
        .priority-1 .priority {
            background-color: #dc3545;
            color: white;
        }
        .priority-2 .priority {
            background-color: #ffc107;
            color: #333;
        }
        .priority-3 .priority {
            background-color: #28a745;
            color: white;
        }
        .item .summary {
            margin: 15px 0;
            color: #555;
        }
        .item a {
            color: #007bff;
            text-decoration: none;
            font-weight: 500;
        }
        .item a:hover {
            text-decoration: underline;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #666;
            font-size: 0.9em;
        }
        .ai-badge {
            display: inline-block;
            background-color: #6f42c1;
            color: white;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            margin-left: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📬 Newsletter Digest - {{ date }}</h1>
        <p>Celkem {{ items|length }} nových položek{{ ' (seřazeno AI)' if ai_enabled else '' }}</p>
        
        {% for item in items %}
        <div class="item priority-{{ item.priority }}">
            <div class="source">
                <span class="priority">Priorita {{ item.priority }}</span>
                <strong>{{ item.source_name }}</strong>
                {% if item.ai_score is not none %}
                <span class="ai-badge">AI skóre: {{ "%.2f"|format(item.ai_score) }}</span>
                {% endif %}
            </div>
            <h2>{{ item.title }}</h2>
            <div class="summary">{{ item.summary }}</div>
            {% if item.link %}
            <a href="{{ item.link }}" target="_blank">Číst celý článek →</a>
            {% endif %}
        </div>
        {% endfor %}
        
        <div class="footer">
            <p>Vygenerováno automaticky · Newsletter Aggregator</p>
        </div>
    </div>
</body>
</html>
"""


def generate_digest_html(items: List[Dict[str, Any]], ai_enabled: bool = False) -> str:
    """
    Vygeneruje HTML digest z položek.
    
    Args:
        items: Seznam položek digestu
        ai_enabled: Zda bylo použito AI pro řazení
        
    Returns:
        HTML string
    """
    template = Template(HTML_TEMPLATE)
    
    html = template.render(
        items=items,
        date=datetime.now().strftime('%d.%m.%Y'),
        ai_enabled=ai_enabled
    )
    
    return html
