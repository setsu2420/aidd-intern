# PD-L1 Binder Design Research Memo

Last reviewed: 2026-05-16

Target: PD-L1, also known as CD274 or B7-H1.

Scope: design intelligence for de novo protein binders, mini-binders, antibody
epitope analysis, interface engineering, and autonomous computational protein
design workflows.

Key sources checked for factual anchors:

- RCSB PDB entries: 4ZQK, 3BIK, 3BIS, 5X8M, 5XXY, 5GRJ, 5JDS, 5J89, 5J8O,
  5N2D, 5N2F, 5JXE, 5WT9, 5GGS, 5GGR, 6NM7, 7DCV.
- UniProt / NCBI RefSeq-style topology and PTM annotations for CD274/PD-L1.
- Structural literature on PD-1/PD-L1 checkpoint blockade antibodies and
  biphenyl small-molecule PD-L1 dimerizers.

## 1. Executive Design Summary

PD-L1 is a good but nontrivial binder-design target. It is clinically validated,
extracellular, structurally compact, and has many solved complexes that expose
actionable epitope geometry. The design problem is not target uncertainty; it
is interface physics. The PD-1-binding face of PD-L1 is broad, shallow, and
immunoglobulin-like, with a hydrophobic stripe rather than a deep enzyme-like
pocket. A naive de novo design pipeline can easily optimize AlphaFold-style
confidence while failing to produce real affinity.

Designability assessment:

- Interface difficulty: medium-high. The PD-1 interface is accessible and
  repeatedly drugged by antibodies, nanobodies, and induced-dimer small
  molecules, but it is flatter than ideal for small mini-binders.
- Pocket depth: low on the monomeric PD-1 face; moderate only when exploiting
  induced PD-L1 dimer pockets used by BMS-like small molecules.
- Surface topology: IgV beta-sandwich face with local ridges and hydrophobic
  patches. Best binders should present complementary beta-edge, loop, or mixed
  helix-loop surfaces rather than a single ideal helix.
- Glycosylation concern: high. PD-L1 has multiple N-linked glycosylation sites;
  glycan occupancy can shield or reshape approach vectors. Designs trained or
  docked only on deglycosylated crystal constructs may fail on cells.
- Expected affinity difficulty: antibodies can reach high affinity because
  they cover large, flexible epitopes. De novo mini-binders will likely require
  either multivalent avidity, epitope focusing on hydrophobic hotspots, or
  scaffold classes with extended loop engagement.

Most promising modalities:

- Antibody: highest precedent and developability confidence; best for direct
  PD-1 blockade epitopes.
- Nanobody / small protein scaffold: strong option because 5JDS demonstrates
  that a compact single-domain binder can engage PD-L1 at high structural
  resolution.
- De novo protein / mini-binder: feasible but should be constrained by hotspot
  and glycan-aware approach geometry; avoid purely helical binder assumptions.
- Cyclic peptide: possible for local hotspot patches, but the flat PD-1 face
  makes high-affinity monovalent cyclic peptides harder unless macrocycle
  design exploits a dimer pocket or an edge groove.
- Helical binder: lower-priority as a first pass. A helix can decorate the
  hydrophobic stripe, but the interface lacks a classic long helical groove.

Overall, PD-L1 is designable if the campaign is framed as epitope-engineered
surface recognition, not pocket docking.

## 2. Structural Biology Deep Dive

### Protein architecture

PD-L1 is a type I membrane protein. The binder-relevant region is the
extracellular domain, which contains an N-terminal IgV-like domain followed by
an IgC-like domain. The N-terminal IgV domain carries the PD-1-binding face and
most therapeutic antibody blockade epitopes. The C-terminal IgC domain is
important for overall extracellular presentation, spacing from the membrane,
glycosylation context, and construct stability, but most direct checkpoint
blockade designs focus on the IgV face.

Approximate topology useful for construct design:

- Signal peptide: N terminus before mature extracellular PD-L1.
- Extracellular region: roughly residues 19-238, containing IgV and IgC domains.
- Transmembrane helix: roughly residues 239-259.
- Cytoplasmic tail: roughly residues 260-290.
- Oligomeric state: PD-L1 is commonly treated as monomeric on the cell surface,
  but small molecules can induce PD-L1 dimerization by binding at a composite
  interface. Do not assume all soluble PDB assemblies represent the cell-surface
  signaling state.
- Disordered regions: terminal segments and construct-specific linkers are
  often absent or engineered in crystal structures; membrane-proximal
  orientation is underrepresented in soluble ectodomain structures.

### PDB analysis

Structure audit table:

| Structure | Resolution / method | Biological assembly | Interface geometry | Missing loops / glycosylation presence | Ligand / binder relevance | Why it matters for design |
| --- | --- | --- | --- | --- | --- | --- |
| 4ZQK | 2.45 A, X-ray | Soluble PD-1 / PD-L1 1:1 ectodomain complex | Native broad IgV/IgV checkpoint interface; shallow, mixed hydrophobic-polar face | Soluble construct; glycans are not a reliable native-cell glycan model; check engineered/missing terminal segments before direct constraint generation | Native receptor-ligand complex | Primary competitive blockade template and hotspot mask |
| 3BIK | 2.65 A, X-ray | Early soluble PD-1 / PD-L1 complex | Native receptor-ligand geometry, useful comparison to 4ZQK | Soluble construct; limited glycan context | Native receptor-ligand complex | Separates stable native interface features from one-template artifacts |
| 3BIS | 2.64 A, X-ray | PD-L1 apo ectodomain | No binder interface; exposes apo IgV surface shape | Soluble construct; limited glycan context; terminal/loop completeness must be checked per chain | Apo reference | Detects binder-induced unrealistic target rearrangements |
| 5X8M | 2.661 A, X-ray | PD-L1 / durvalumab Fab complex | Broad antibody CDR footprint overlapping the PD-1 face | Fab/soluble PD-L1 construct; native glycan shielding not fully represented | Therapeutic anti-PD-L1 antibody | Shows antibody-scale solution to flat-interface blockade |
| 5XXY | 2.9 A, X-ray | PD-L1 / atezolizumab Fab complex | Broad CDR-mediated blockade epitope on IgV face | Moderate resolution; construct/glycan state should not be treated as full cell-surface context | Therapeutic anti-PD-L1 antibody | Independent antibody footprint for epitope clustering |
| 5GRJ | 3.206 A, X-ray | PD-L1 / avelumab Fab complex | Broad antibody footprint; lower side-chain confidence | Lower resolution; use for epitope-level reasoning rather than atom-level rotamers; glycan context incomplete | Therapeutic anti-PD-L1 antibody | Third antibody footprint for recurrent epitope inference |
| 5JDS | 1.7 A, X-ray | PD-L1 / nanobody complex | Compact loop-rich paratope engaging PD-L1 with high local complementarity | Soluble construct; check glycan compatibility of approach vector separately | Nanobody binder | Best small-scaffold precedent for mini-binder design |
| 5J89 | 2.2 A, X-ray | PD-L1 dimer stabilized by low molecular mass inhibitor | Composite hydrophobic pocket formed at induced PD-L1 dimer interface | Dimer state is ligand-induced; glycan and membrane geometry not native by default | Small-molecule inhibitor / dimerizer | Reveals deeper composite pocket unavailable in monomer-only design |
| 5J8O | 2.3 A, X-ray | PD-L1 dimer with low molecular mass inhibitor | Similar induced dimer pocket, alternate ligand-bound state | Same dimer/glycan caveats as 5J89 | Small-molecule inhibitor / dimerizer | Tests robustness of dimer-pocket interpretation |
| 5N2D | 2.35 A, X-ray | PD-L1 / small-molecule inhibitor complex | Ligand-stabilized hydrophobic pocket and dimer-related contacts | Inhibitor-induced state; limited native glycan context | Small-molecule inhibitor | Supports allosteric/dimer-stabilizing design hypotheses |
| 5N2F | 1.7 A, X-ray | PD-L1 / small-molecule inhibitor complex | High-resolution view of inhibitor pocket contacts | Inhibitor-induced state; not a native monomeric pocket guarantee | Small-molecule inhibitor | Best high-resolution pocket geometry among inhibitor templates |
| 5JXE | 2.9 A, X-ray | PD-1 / pembrolizumab Fab complex | Receptor-side antibody blockade, not PD-L1 binding | PD-1 construct; not a PD-L1 glycan model | Therapeutic anti-PD-1 antibody | Pathway control; prevents confusing PD-1 epitopes with PD-L1 epitopes |
| 5WT9 | 2.401 A, X-ray | PD-1 / nivolumab Fab complex | Receptor-side antibody blockade | PD-1 construct; not PD-L1 | Therapeutic anti-PD-1 antibody | Defines receptor-side blockade geometry for mechanism comparison |
| 7DCV | Solution NMR | PD-L1 transmembrane domain | Membrane helix, not soluble ectodomain interface | No soluble ectodomain glycans; informs membrane context only | Membrane orientation reference | Useful for membrane-proximal steric hypotheses |

#### 4ZQK: human PD-1 / PD-L1 complex, 2.45 A

This is the central design template for direct PD-1 blockade. It captures the
PD-L1 IgV face bound to PD-1 and exposes the topology that a competitive binder
must occlude. The biological assembly is a 1:1 receptor-ligand complex between
soluble ectodomains. Its design relevance is high because it identifies the
native checkpoint interface rather than an antibody-selected epitope.

Design interpretation:

- The interface is extended and relatively flat, with local hydrophobic and
  polar patches.
- PD-L1 residues around the GFCC'C''-like face, including the Tyr56 / Glu58
  region and the Met115 / Ala121 / Tyr123 region, are central design anchors.
- Missing loops and deglycosylation/construct choices must be checked before
  using it as the only modeling template.
- Use 4ZQK to define competitive blockade constraints and hotspot masks for
  RFdiffusion or ProteinMPNN-conditioned redesign.

#### 3BIK and 3BIS: early PD-1/PD-L1 complex and PD-L1 apo structures, about 2.65 A

These structures are useful for separating native conformational features from
later construct- or antibody-induced conformations. 3BIS is especially useful
as a monomeric PD-L1 reference, while 3BIK provides an early receptor-complex
view.

Design interpretation:

- Compare apo and PD-1-bound IgV surfaces to identify flexible loops that may
  tolerate binder-induced conformational changes.
- Use apo PD-L1 to detect whether candidate binders require unrealistic local
  rearrangements.
- Do not overfit to one PD-1 complex; compare 3BIK and 4ZQK to identify stable
  interface features.

#### 5X8M: PD-L1 / durvalumab complex, 2.661 A

Durvalumab binds the PD-L1 IgV domain and blocks PD-1 by occupying overlapping
surface real estate. The Fab interface shows how an antibody uses multiple CDRs
to solve the flat-interface problem.

Design interpretation:

- This structure is a positive control for high-affinity broad-surface
  blockade.
- CDR-like loops cover a surface larger and more conformationally adaptable
  than most small mini-binders can cover.
- For de novo binders, mine the antibody footprint for recurrent hotspots but
  avoid copying the entire antibody-sized epitope unless designing a large
  scaffold.

#### 5XXY: PD-L1 / atezolizumab complex, 2.9 A

Atezolizumab is another direct PD-L1 blockade antibody. Its structure gives an
independent antibody solution to the same surface-recognition problem.

Design interpretation:

- Compare 5XXY with 5X8M and 5GRJ to identify antibody-convergent epitope
  regions.
- Regions repeatedly contacted by unrelated antibodies are likely
  design-relevant hotspots, but also crowded intellectual and functional
  epitope space.
- The moderate resolution means side-chain details should be used for epitope
  mapping, not atomic-level rotamer copying.

#### 5GRJ: PD-L1 / avelumab complex, 3.206 A

Avelumab binds PD-L1 and blocks PD-1 while preserving an Fc-mediated therapeutic
format. The resolution is lower than ideal for fine atom placement but still
useful for epitope-level reasoning.

Design interpretation:

- Use for epitope overlap and approach-vector comparison, not fine-grained
  hydrogen-bond templates.
- Its epitope helps distinguish broadly antibody-accessible PD-L1 regions from
  one-off construct artifacts.
- Lower resolution should reduce confidence in individual side-chain
  conclusions.

#### 5JDS: PD-L1 / nanobody complex, 1.7 A

This is particularly important for mini-binder design because it demonstrates
that a compact single-domain binder can engage PD-L1 with high-resolution
structural complementarity.

Design interpretation:

- Treat as a scaffold-size precedent for non-IgG binder strategies.
- The nanobody paratope can inspire loop-rich de novo scaffold constraints.
- Because nanobodies often use protruding CDR3-like loops, this supports
  designing binders with local protrusions that reach into shallow surface
  depressions, rather than smooth convex helices.

#### 5J89, 5J8O, 5N2D, 5N2F: PD-L1 / small-molecule inhibitor complexes, 1.7-2.35 A

These structures show biphenyl-like small molecules binding PD-L1 and inducing
or stabilizing PD-L1 dimerization. They matter because they reveal a composite
hydrophobic pocket not obvious from a single PD-L1 monomer.

Design interpretation:

- These complexes expose a ligand-induced dimer pocket involving hydrophobic
  residues on two PD-L1 IgV domains.
- This is not the same design problem as mimicking PD-1. It suggests
  dimer-stabilizing or allosteric protein binders could be designed, but their
  biology and cell-surface geometry must be validated.
- A protein binder that stabilizes the wrong PD-L1 oligomer could have
  unexpected functional effects.

#### 5JXE, 5WT9, 5GGS, 5GGR: PD-1 / pembrolizumab or nivolumab complexes

These are not PD-L1 binder structures, but they matter for competitive pathway
engineering. Pembrolizumab and nivolumab bind PD-1, not PD-L1, and block the
checkpoint from the receptor side.

Design interpretation:

- Use these structures to understand the PD-1 surface that PD-L1 naturally
  sees and how receptor-side antibodies compete.
- They are negative controls for PD-L1 binder campaigns: do not confuse PD-1
  epitopes with PD-L1 epitopes.
- They help define whether a PD-L1 binder should be strictly competitive with
  PD-1 or could avoid receptor-side antibody overlap.

#### 6NM7: PD-L1 IgV fragment complex, 2.426 A

This structure shows ligand recognition on the PD-L1 IgV domain and is useful
for fragment/pocket reasoning.

Design interpretation:

- Use it to identify local ligandable patches that may support macrocycle or
  constrained-loop design.
- Fragment-bound conformations should be checked against full ectodomain and
  antibody complexes before using them as de novo binder constraints.

#### 7DCV: PD-L1 transmembrane domain, solution NMR

The transmembrane helix is outside the standard soluble binder design problem,
but it informs membrane orientation and membrane-proximal epitope feasibility.

Design interpretation:

- Soluble ectodomain designs may not capture membrane-proximal sterics.
- If designing membrane-proximal or dimer-stabilizing binders, include membrane
  orientation and local concentration effects in the model.

## 3. PD-1 / PD-L1 Interface Analysis

### Hotspot residues

The PD-1 / PD-L1 interface concentrates design-relevant contacts on the PD-L1
IgV domain. Recurrently important PD-L1 residues include:

- Tyr56 and Glu58 region: a mixed aromatic/polar patch near the N-terminal IgV
  face. Tyr56 is a strong hydrophobic/aromatic anchor; Glu58 contributes polar
  and electrostatic complementarity.
- Arg113 and Met115 region: Arg113 can contribute charged/polar anchoring,
  while Met115 is part of a hydrophobic stripe important in both receptor and
  inhibitor-bound interpretations.
- Ala121, Asp122, Tyr123 region: Tyr123 is a major aromatic hotspot; Ala121
  shapes the hydrophobic surface; Asp122 affects local polar boundary
  conditions.
- Additional nearby beta-strand and loop residues shape the shallow receptor
  face; exact residue inclusion should be template-specific and chain-numbering
  checked before constraint generation.

Hydrophobic hotspots are more designable than purely polar contacts because
they can drive burial and shape complementarity. For PD-L1, the Tyr56 / Met115
// Tyr123-like hydrophobic strip is the most attractive de novo anchor. The
risk is hydrophobic collapse: a model can bury the binder against itself or
create a sticky nonspecific surface rather than a well-packed PD-L1 interface.

### Interface geometry

PD-1 / PD-L1 is not a deep-pocket interaction. It is a broad protein-protein
interface with:

- moderate buried solvent-accessible surface area rather than a small hot
  pocket;
- limited concavity on the PD-L1 side;
- mixed hydrophobic and polar patches;
- local beta-sheet-like edge geometry and loop-mediated complementarity;
- enough flatness that many AF-Multimer false positives can look plausible.

Design implication: interface complementarity must be evaluated with explicit
shape and energy metrics, not confidence alone. A binder should bury the
hydrophobic stripe without creating large unsatisfied polar groups or an
excessive exposed hydrophobic rim.

### Design implications

Suitable scaffold classes:

- loop-rich mini-proteins with one protruding loop and one stabilizing secondary
  structure element;
- nanobody-inspired small scaffolds;
- designed repeat/scaffold proteins with extended surfaces;
- beta-hairpin or mixed beta/loop binders if backbone generation can control
  edge aggregation risk;
- bivalent or avidity-enhanced formats for lower-affinity monomers.

Likely failure modes:

- helix-only binders that contact only a narrow hydrophobic stripe and fail to
  reach sufficient buried area;
- AF reward hacking with high pLDDT but poor experimental binding;
- excessive hydrophobic surface causing aggregation;
- designs that ignore glycans and bind an inaccessible approach vector;
- binders that bind soluble PD-L1 but fail on membrane-presented PD-L1.

## 4. Epitope Intelligence

Known therapeutic PD-L1 antibodies converge on the IgV domain and frequently
overlap the PD-1-binding face. This convergence is useful and dangerous: it
identifies validated blockade epitopes, but it also means many obvious design
hypotheses will simply rediscover crowded antibody space.

Epitope classes:

- PD-1-competitive central face: includes the native receptor-contact surface
  seen in 4ZQK. Best for direct checkpoint blockade and easiest to benchmark.
- Antibody-convergent blockade region: sampled by atezolizumab, durvalumab, and
  avelumab complexes. Best for functional blockade, but sterically broad.
- Nanobody-accessible compact epitope: 5JDS suggests that smaller paratopes can
  exploit local protrusions/depressions.
- Small-molecule-induced dimer epitope: 5J89 / 5N2-series structures reveal
  composite hydrophobic pockets; potentially novel but biologically riskier.
- Membrane-proximal / noncompetitive regions: less crowded, but functional
  blockade is less guaranteed and cell-surface accessibility is harder.

Best epitopes for de novo binders:

- A hotspot-focused patch overlapping PD-1 and antibody epitopes, especially if
  the binder can use a loop to cover Tyr56 / Met115 / Tyr123-like anchors.
- Nanobody-like compact epitopes with high local shape complementarity.
- Dimer-pocket-inspired epitopes only if the project explicitly wants
  allosteric or dimer-stabilizing mechanisms.

Overcrowded regions:

- The exact central PD-1 blockade face is heavily sampled by antibodies and
  small molecules. Novelty requires either a different approach vector, a
  smaller scaffold, or a distinct mechanism.

Novelty opportunities:

- glycan-aware epitopes adjacent to but not identical with antibody footprints;
- membrane-orientation-aware binders that exploit approach vectors unavailable
  to soluble Fabs;
- binders that stabilize a nonproductive PD-L1 arrangement rather than simply
  occluding PD-1.

## 5. Glycosylation & PTM Analysis

PD-L1 glycosylation is a first-order design constraint. Reported N-linked
glycosylation sites include Asn35, Asn192, Asn200, and Asn219 in the
extracellular domain. These sites are not all on the central PD-1 face, but
they affect construct behavior, protein stability, immune recognition, and
cell-surface accessibility.

Design implications:

- Crystal structures often use engineered, truncated, or deglycosylated
  constructs. A design that looks ideal on a crystal construct may clash with
  glycans on native tumor-cell PD-L1.
- Glycans can shield approach vectors even when they do not directly cover the
  hotspot residues.
- Tumor-specific glycosylation heterogeneity can change apparent binding
  kinetics across cell lines.
- AlphaFold/RFdiffusion-style workflows generally ignore glycans unless they
  are explicitly modeled post hoc.

Practical workflow:

1. Generate designs against the protein-only structure for speed.
2. Add representative N-glycans to Asn35, Asn192, Asn200, and Asn219 for
   steric filtering.
3. Reject designs whose approach vector collides with plausible glycan
   envelopes.
4. Validate top designs against both deglycosylated and glycosylated PD-L1
   models.
5. In wet lab, compare binding to glycosylated mammalian PD-L1 versus
   deglycosylated or bacterial material.

Failure risk: a binder can show beautiful soluble ectodomain binding but lose
cell binding because its paratope enters from a glycan-shielded or
membrane-incompatible direction.

## 6. Existing Therapeutic Landscape

The therapeutic lesson is structural, not just clinical: successful checkpoint
antibodies solve a broad, shallow protein-protein interface by using multiple
CDRs to create a large adaptable surface.

### Atezolizumab

Atezolizumab binds PD-L1 and blocks PD-1 from the ligand side. The 5XXY complex
shows an antibody solution to broad-surface recognition. Its design lesson is
that high-affinity blockade uses distributed contacts rather than one small
pocket. De novo binders trying to miniaturize this epitope must decide which
hotspots to preserve and which antibody contacts to abandon.

### Durvalumab

Durvalumab, represented by 5X8M, binds the PD-L1 IgV face and occludes receptor
engagement. It is a strong template for approach-vector and footprint analysis.
The design lesson is that overlapping the PD-1 face is sufficient for blockade,
but a smaller binder must compensate for lost antibody contact area with better
shape complementarity or avidity.

### Avelumab

Avelumab binds PD-L1 in 5GRJ. Although the structure is lower resolution, it
adds an independent antibody footprint for epitope clustering. Its lesson for
design is that several antibody solutions can converge on similar functional
surface regions while using different CDR geometries.

### Pembrolizumab and nivolumab

Pembrolizumab and nivolumab bind PD-1, not PD-L1. Their PD-1 complexes such as
5JXE, 5WT9, 5GGS, and 5GGR are still useful because they define receptor-side
blockade logic and the PD-1 surface that competes with PD-L1. For a PD-L1
binder campaign, they are pathway controls rather than direct PD-L1 epitope
templates.

Developability lessons:

- Antibodies tolerate broad epitopes and glycan-adjacent approach vectors
  better than tiny binders.
- Functional blockade does not require mimicking PD-1 exactly; it requires
  sterically preventing productive PD-1 / PD-L1 engagement.
- Smaller scaffolds need more rigorous aggregation and nonspecific-binding
  filters because hydrophobic hotspot targeting can create sticky surfaces.

## 7. Computational Design Strategy Recommendations

Recommended pipeline:

1. Structure curation.
   - Align 4ZQK, 3BIK, 3BIS, 5X8M, 5XXY, 5GRJ, 5JDS, and 5J89-like complexes.
   - Define PD-1-competitive, antibody-convergent, nanobody-like, and
     dimer-pocket epitope masks.
   - Generate protein-only and glycan-envelope target models.
2. Hotspot and approach-vector selection.
   - Prioritize Tyr56 / Glu58, Arg113 / Met115, Ala121 / Asp122 / Tyr123-like
     patches, but verify numbering in the chosen PDB chain.
   - Reject approach vectors that collide with modeled glycans or membrane.
3. Backbone generation.
   - Use RFdiffusion or equivalent constrained diffusion for hotspot-focused
     mini-binders.
   - Use PXdesign for high-throughput backbone and sequence co-design.
   - Use BoltzGen when constraints require site-specific or topology-aware
     generation.
   - Use BindCraft for iterative AF2/ProteinMPNN/PyRosetta refinement of
     promising seeds.
4. Sequence optimization.
   - Use ProteinMPNN with interface constraints, not unconstrained global
     redesign.
   - Penalize exposed hydrophobics and sequence repeats.
   - Preserve designed core stability while varying interface residues for
     sequence diversity.
5. Cheap filters.
   - Monomer pLDDT and predicted secondary-structure sanity.
   - Interface buried SASA.
   - Unsatisfied polar atoms.
   - Exposed hydrophobic surface.
   - Aggregation and developability predictors.
6. Expensive filters.
   - AlphaFold-Multimer or equivalent complex prediction.
   - Chai-1 and Protenix orthogonal validation.
   - Rosetta interface ΔΔG and packing analysis.
   - Foldseek / TM-align clustering.
   - Short restrained MD for top designs, especially glycan-adjacent binders.

RFdiffusion suitability:

- Suitable for generating constrained mini-binder backbones against hotspot
  patches.
- Risky if given an overly broad flat surface without explicit hotspot
  constraints; the model may produce plausible but weak binders.

ProteinMPNN usage:

- Use after backbone generation to diversify interface and core sequences.
- Apply interface-aware constraints and filter for developability.
- Do not use MPNN diversity as evidence of binding; it is sequence feasibility,
  not affinity.

AlphaFold-Multimer limitations:

- High confidence can arise from learned interface priors or co-folding
  artifacts.
- AF confidence does not prove kinetic accessibility, concentration-dependent
  binding, glycan compatibility, or membrane-context binding.

Rosetta and MD:

- Rosetta interface metrics are necessary to detect packing defects and
  unsatisfied polar atoms.
- MD is not a high-throughput filter, but it is useful for top candidates with
  marginal interface packing or glycan-adjacent approach vectors.

Foldseek:

- Use Foldseek to cluster final binders and avoid delivering a redundant family
  of the same backbone solution.
- Cluster both binder monomers and complex geometries; monomer diversity alone
  does not guarantee epitope diversity.

## 8. Failure Modes & Risks

AF reward hacking:

- A design can achieve high pLDDT and favorable ipTM by presenting a
  model-friendly interface that does not bind experimentally.
- AF-derived confidence is a hypothesis generator, not a binding assay.

Flat-interface problems:

- PD-L1's central face lacks a deep pocket, so small binders may not bury
  enough area.
- A binder may slide on the surface or adopt multiple shallow poses.

Hydrophobic collapse:

- Targeting Tyr56 / Met115 / Tyr123-like hydrophobic regions can select sticky
  hydrophobic paratopes.
- Such designs may aggregate or bind serum proteins nonspecifically.

Glycosylation mismatch:

- Protein-only structures omit glycan shielding.
- Designs can fail on mammalian cell PD-L1 despite binding recombinant,
  deglycosylated PD-L1.

False-positive interfaces:

- AF-Multimer and related models can over-stabilize artificial interfaces,
  especially when the binder is co-designed with the target.
- Cross-validation with Chai-1 and Protenix reduces but does not eliminate this
  risk.

Sequence degeneracy:

- ProteinMPNN may produce many sequences for the same backbone that look
  diverse but retain the same flawed interface geometry.

Developability issues:

- Small protein scaffolds can expose hydrophobic patches, contain protease
  liabilities, or have poor expression.
- Antibody-like loops may create liabilities if not constrained for stability.

Experimental translation risk:

- Soluble binding does not guarantee cell-surface blockade.
- Functional blockade requires competition with PD-1 in the correct membrane
  geometry and expression context.

Why high AF confidence does not guarantee real binding:

- AF confidence estimates structural plausibility under the model, not binding
  free energy.
- It does not measure on-rate, off-rate, avidity, glycan sterics, membrane
  accessibility, expression, aggregation, or immune-complex behavior.
- It can be reward-hacked by designing interfaces similar to patterns in
  training data.

## 9. Hypothesis-Driven Binder Design Ideas

### Hypothesis 1: hotspot-focused competitive mini-binder

Rationale: block PD-1 by occupying the central IgV hotspot stripe.

Structural basis: anchor against Tyr56 / Met115 / Tyr123-like hydrophobic
features and satisfy adjacent polar boundaries around Glu58 / Arg113 / Asp122.

Advantages:

- Directly benchmarkable against PD-1 competition.
- Uses the most validated functional epitope.

Risks:

- Flat interface may produce weak monovalent affinity.
- Hydrophobic paratope may aggregate.
- Glycan approach vectors must be checked.

Validation:

- SPR/BLI binding to glycosylated PD-L1.
- PD-1 competition assay.
- Cell-surface PD-L1 binding.
- Mutational scan around Tyr56 / Met115 / Tyr123-like residues.

### Hypothesis 2: nanobody-inspired loop-rich scaffold

Rationale: 5JDS demonstrates compact binder feasibility.

Structural basis: design a stabilized small scaffold with one protruding loop
to penetrate local shallow depressions and a second surface to bury the
hydrophobic stripe.

Advantages:

- More realistic than a smooth helix-only mini-binder.
- Smaller than Fab but still loop-adaptable.

Risks:

- Loop flexibility can reduce affinity.
- Designed loops can create expression or stability liabilities.

Validation:

- Compare against 5JDS-like approach vectors.
- Run loop alanine scanning.
- Test thermal stability and expression yield.

### Hypothesis 3: glycan-aware edge binder

Rationale: avoid the most crowded antibody footprint while exploiting a
glycan-compatible approach vector.

Structural basis: bind adjacent to the PD-1 face, partially overlapping the
receptor interface but entering between glycan envelopes.

Advantages:

- Potential epitope novelty.
- May improve cellular translation if explicitly glycan-filtered.

Risks:

- Partial overlap may not fully block PD-1.
- Glycan heterogeneity may make binding context-dependent.

Validation:

- Compare binding to glycosylated and enzymatically deglycosylated PD-L1.
- Cell-line panel with different glycosylation states.
- PD-1 competition and functional reporter assays.

### Hypothesis 4: PD-L1 dimer-stabilizing allosteric binder

Rationale: BMS-like small molecules reveal that PD-L1 can be inhibited through
induced dimerization.

Structural basis: design a protein binder that stabilizes a nonproductive
PD-L1 dimer or composite hydrophobic pocket.

Advantages:

- Mechanistically novel relative to direct PD-1 mimicry.
- Could exploit a deeper composite pocket.

Risks:

- Cell-surface geometry may not allow the designed dimer.
- Dimer stabilization could have unexpected biology.
- High risk of nonspecific hydrophobic binding.

Validation:

- SEC-MALS or native MS for dimer induction.
- Cell-surface crosslinking/FRET.
- Functional blockade assays compared with direct competitive binders.

### Hypothesis 5: membrane-proximal steric blocker

Rationale: instead of perfectly mimicking PD-1, block productive engagement by
steric interference near the cell membrane.

Structural basis: use ectodomain plus transmembrane-orientation models to
identify approach vectors near the IgC/membrane-proximal region.

Advantages:

- Less crowded epitope space.
- Potential for avidity formats on cell surfaces.

Risks:

- Soluble assays may not predict function.
- Membrane context is hard to model.
- May not block PD-1 if steric geometry is wrong.

Validation:

- Cell-based PD-1/PD-L1 reporter assays.
- Soluble versus membrane-tethered PD-L1 binding comparison.
- Orientation-sensitive microscopy or proximity assays.

## 10. Benchmark & Evaluation Suggestions

Computational metrics:

- ipTM: useful for complex confidence, but reward-hackable.
- pAE_interaction: good for detecting uncertain relative orientation; still
  model-dependent.
- DockQ: useful when comparing to known receptor or antibody complex poses.
- Rosetta ΔΔG: useful for packing/energy sanity; sensitive to input pose.
- Buried SASA: necessary but insufficient; large buried area can be nonspecific.
- Interface complementarity: more trustworthy when combined with unsatisfied
  polar and hydrophobic exposure checks.
- Aggregation prediction: essential for hydrophobic hotspot binders.
- Sequence diversity: useful only after clustering by backbone and epitope.

Structural metrics:

- interface RMSD across AF-Multimer, Chai-1, and Protenix;
- fraction of interface residues conserved across validation models;
- glycan-envelope clash score;
- membrane approach-vector compatibility;
- Foldseek cluster count among passing designs.

Wet-lab proxy metrics:

- SPR/BLI affinity and kinetics against glycosylated mammalian PD-L1;
- PD-1 competition ELISA or BLI;
- cell-surface binding by flow cytometry;
- reporter assay blockade;
- thermal stability and expression yield;
- nonspecific binding and aggregation assays.

Metrics most easily reward-hacked:

- ipTM alone;
- pLDDT alone;
- sequence diversity without structural diversity;
- buried SASA without interface quality;
- one-model AF-Multimer pass rate.

More trustworthy metric combinations:

- Chai-1 / Protenix agreement plus low pAE_interaction;
- Rosetta interface energy plus low unsatisfied polar atoms;
- glycan/membrane clash filtering plus cell-surface binding;
- Foldseek cluster diversity plus independent epitope diversity;
- mutational validation of predicted hotspot dependence.

Experimental prioritization:

1. Select top designs from multiple structural clusters, not the top 20 from
   one backbone family.
2. Include negative controls that intentionally miss Tyr56 / Met115 /
   Tyr123-like anchors.
3. Test glycosylated mammalian PD-L1 early.
4. Prioritize designs with interpretable hotspot dependence over black-box
   high-confidence interfaces.

## 11. Open Questions & Future Directions

- Which PD-L1 glycoforms dominate the intended tumor context, and do they
  shield the planned approach vector?
- Can a de novo mini-binder bury enough surface on the PD-1 face without
  becoming hydrophobic and aggregation-prone?
- Is a nanobody-inspired loop-rich scaffold a better first campaign than a
  helix-first RFdiffusion binder?
- Are dimer-stabilizing mechanisms desirable for the intended therapeutic
  hypothesis, or should the first campaign remain strictly PD-1 competitive?
- Which structures should define the canonical numbering and epitope mask for
  automated tools?
- How should the autonomous agent decide when to expand sampling versus switch
  epitope hypotheses?
- What wet-lab proxy best predicts final function: PD-1 competition, reporter
  blockade, or cell-surface binding under glycan-native conditions?

Recommended next step: build a curated PD-L1 target bundle containing aligned
PDBs, glycan-envelope models, hotspot masks, antibody/nanobody epitope masks,
and a small benchmark set for with-harness versus without-harness comparison.
