"""Automatiserede tests. Kør: python -m unittest discover -s tests -t ."""
import logging

# Forventede advarsler (fx "opretter standardbrugeren admin") skal ikke fylde
# testoutputtet. Fejl i koden vises stadig som fejlede tests.
logging.disable(logging.WARNING)
