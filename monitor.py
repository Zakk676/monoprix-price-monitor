import json
import os
import re

import requests
from bs4 import BeautifulSoup


PRODUCTS_FILE = "products.json"
PRICES_FILE = "prices.json"


def get_price(url):
    """Récupère le prix actuel d'une page produit."""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # 1. Recherche dans les données structurées JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())

            items = data if isinstance(data, list) else [data]

            for item in items:
                if not isinstance(item, dict):
                    continue

                offers = item.get("offers")

                if isinstance(offers, dict):
                    price = offers.get("price")

                    if price is not None:
                        return float(str(price).replace(",", "."))

                elif isinstance(offers, list):
                    for offer in offers:
                        if isinstance(offer, dict) and offer.get("price"):
                            return float(
                                str(offer["price"]).replace(",", ".")
                            )

        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    # 2. Recherche dans les balises meta
    selectors = [
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]'
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element and element.get("content"):
            try:
                return float(
                    element["content"].replace(",", ".")
                )
            except ValueError:
                pass

    # 3. Dernier recours : recherche d'un prix dans le texte
    text = soup.get_text(" ", strip=True)

    matches = re.findall(
        r'(\d{1,4}(?:[.,]\d{2})?)\s*€',
        text
    )

    if matches:
        prices = []

        for match in matches:
            try:
                prices.append(
                    float(match.replace(",", "."))
                )
            except ValueError:
                pass

        if prices:
            return prices[0]

    raise ValueError(
        f"Impossible de trouver le prix : {url}"
    )


def send_email(product_name, url, old_price, new_price):
    """Envoie une alerte email via Resend."""

    api_key = os.environ["RESEND_API_KEY"]
    email_to = os.environ["EMAIL_TO"]

    difference = old_price - new_price
    percentage = (difference / old_price) * 100

    subject = f"🔻 Baisse de prix : {product_name}"

    html = f"""
    <html>
        <body>
            <h2>🔻 Baisse de prix détectée</h2>

            <p><strong>{product_name}</strong></p>

            <p>
                Ancien prix :
                <strong>{old_price:.2f} €</strong>
            </p>

            <p>
                Nouveau prix :
                <strong>{new_price:.2f} €</strong>
            </p>

            <p>
                Baisse :
                <strong>{difference:.2f} € (-{percentage:.1f} %)</strong>
            </p>

            <p>
                <a href="{url}">👉 Voir le produit</a>
            </p>
        </body>
    </html>
    """

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "from": "onboarding@resend.dev",
            "to": [email_to],
            "subject": subject,
            "html": html
        },
        timeout=30
    )

    response.raise_for_status()

    print("📧 Email envoyé avec succès.")


def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    with open(filename, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


def main():

    products = load_json(PRODUCTS_FILE, [])
    old_prices = load_json(PRICES_FILE, {})

    new_prices = old_prices.copy()

    for product in products:

        name = product["name"]
        url = product["url"]

        try:
            current_price = get_price(url)

            print(
                f"{name} : {current_price:.2f} €"
            )

            previous_price = old_prices.get(url)

            # Première vérification :
            # on enregistre le prix sans envoyer d'email.
            if previous_price is None:

                print(
                    f"Prix initial enregistré : "
                    f"{current_price:.2f} €"
                )

            # Baisse détectée
            elif current_price < previous_price:

                print(
                    f"🔻 BAISSE : "
                    f"{previous_price:.2f} € "
                    f"-> {current_price:.2f} €"
                )

                send_email(
                    name,
                    url,
                    previous_price,
                    current_price
                )

            # Hausse ou prix identique
            else:

                print(
                    f"Pas de baisse : "
                    f"{previous_price:.2f} € "
                    f"-> {current_price:.2f} €"
                )

            # Sauvegarde du dernier prix
            new_prices[url] = current_price

        except Exception as error:

            print(
                f"❌ ERREUR pour {name} : {error}"
            )

    save_json(
        PRICES_FILE,
        new_prices
    )


if __name__ == "__main__":
    main()
