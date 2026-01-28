"""
Modul pro AI re-prioritizaci položek digestu pomocí OpenAI API.
Hodnotí položky podle kritérií: akčnost, uzávěrka, důležitost pro učení, potřebnost.
"""
from typing import List, Dict, Any, Optional
import json


def reprioritize(items: List[Dict[str, Any]], api_key: str) -> Dict[str, float]:
    """
    Použije OpenAI API pro přehodnocení priorit položek.
    
    Args:
        items: Seznam položek digestu
        api_key: OpenAI API klíč
        
    Returns:
        Slovník {message_id: ai_score} kde ai_score je 0..1
    """
    if not api_key:
        print("OpenAI API klíč není nastaven, přeskakuji AI re-prioritizaci")
        return {}
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # Připravit data pro AI
        items_summary = []
        for item in items:
            items_summary.append({
                'message_id': item['message_id'],
                'title': item['title'],
                'summary': item['summary'][:200],  # Zkrátit pro úsporu tokenů
                'priority': item['priority'],
                'source': item.get('source_name', 'Unknown')
            })
        
        # Vytvořit prompt
        prompt = f"""Analyzuj následující položky newsletteru a pro každou přiřaď skóre 0-1 podle těchto kritérií:
- Akčnost (actionability): Lze na základě informace okamžitě jednat?
- Blížící se uzávěrka (deadline): Je tam časová citlivost?
- Důležitost pro učení (learning value): Je to důležité pro vzdělávání/rozvoj?
- Potřebnost (need): Je to relevantní pro aktuální potřeby?

Vyšší skóre = důležitější položka.

Položky:
{json.dumps(items_summary, ensure_ascii=False, indent=2)}

Odpověz POUZE ve formátu JSON jako slovník, kde klíč je message_id a hodnota je skóre 0-1:
{{"<message_id>": 0.X, ...}}"""
        
        # Zavolat OpenAI API
        try:
            # Zkusit gpt-4o-mini
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Jsi expert na hodnocení důležitosti newsletterových článků. Odpovídáš pouze ve formátu JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
        except Exception as e:
            print(f"Model gpt-4o-mini selhal, zkouším gpt-3.5-turbo: {e}")
            # Fallback na gpt-3.5-turbo
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Jsi expert na hodnocení důležitosti newsletterových článků. Odpovídáš pouze ve formátu JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
        
        # Parsovat odpověď
        content = response.choices[0].message.content.strip()
        
        # Odstranit markdown code block značky, pokud jsou přítomny
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
            content = content.strip()
        
        scores = json.loads(content)
        
        print(f"AI re-prioritizace úspěšná, získáno {len(scores)} skóre")
        return scores
        
    except Exception as e:
        print(f"Chyba při AI re-prioritizaci: {e}")
        return {}
