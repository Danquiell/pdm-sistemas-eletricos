"""Mantém rota ONS do grupo e adiciona o consumidor INMET independente."""
from ons_legacy import app
from inmet_service import register
register(app)
