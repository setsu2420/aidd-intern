"""Protein binder design workflow compatibility namespace."""

from agent.workflows.protein_design.roles import PROTEIN_DESIGN_ROLES
from agent.roles import register_roles

register_roles(PROTEIN_DESIGN_ROLES)
