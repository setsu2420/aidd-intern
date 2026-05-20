"""Protein binder design domain pack."""

from agent.domain_packs.protein_design.roles import PROTEIN_DESIGN_ROLES
from agent.roles import register_roles

register_roles(PROTEIN_DESIGN_ROLES)
