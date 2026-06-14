"""
Foreign Exchange Client
=======================

Wraps the Frankfurter API for historical exchange rates.
Free, no API key required.
Base URL: https://api.frankfurter.app/

Rates are cached in Django's cache framework to avoid hitting the
API repeatedly for the same date during a bulk import.
"""

import logging
from decimal import Decimal

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)


class FXClient:
    """
    Fetches historical FX rates from the Frankfurter API.

    Usage::

        client = FXClient()
        rate = client.get_rate('USD', 'INR', '2026-03-09')
        # → Decimal('83.45')
    """

    BASE_URL = "https://api.frankfurter.app"

    def get_rate(self, from_currency: str, to_currency: str, date: str) -> Decimal:
        """
        Gets the exchange rate for a specific date.

        Args:
            from_currency: ISO 4217 code (e.g. 'USD')
            to_currency:   ISO 4217 code (e.g. 'INR')
            date:          'YYYY-MM-DD' format

        Returns:
            Decimal rate (e.g. ``Decimal('83.45')`` for USD→INR)

        Raises:
            ValueError: if rate cannot be fetched and no fallback exists
                        (triggers FOREIGN_CURRENCY anomaly upstream)
        """
        # Same currency → identity rate, no API call needed
        if from_currency == to_currency:
            return Decimal('1.0')

        # Check Django cache first (avoids redundant API hits during bulk import)
        cache_key = f"fx_rate_{from_currency}_{to_currency}_{date}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Decimal(str(cached))

        try:
            url = f"{self.BASE_URL}/{date}?from={from_currency}&to={to_currency}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            rate = Decimal(str(data['rates'][to_currency]))
            # Cache for 24 hours — historical rates don't change
            cache.set(cache_key, str(rate), 60 * 60 * 24)
            return rate

        except Exception as e:
            logger.error(
                f"FX rate fetch failed for {from_currency}->{to_currency} "
                f"on {date}: {e}"
            )
            # Fallback: use hardcoded approximate rates and flag the anomaly
            fallback_rates = {
                'USD': Decimal('84.00'),
                'EUR': Decimal('91.00'),
                'GBP': Decimal('106.00'),
            }
            fallback = fallback_rates.get(from_currency)
            if fallback:
                logger.warning(
                    f"Using fallback rate {fallback} for {from_currency}"
                )
                return fallback

            raise ValueError(
                f"Cannot fetch exchange rate for {from_currency} on {date}"
            )
