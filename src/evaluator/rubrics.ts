export interface Rubric { name: string; description: string; dimensions: { name: string; description: string; weight: number; criteria: string[] }[]; maxScore: number; }
export const GENERAL_CAPABILITY_RUBRIC: Rubric = { name: 'General', description: 'Overall agent performance', maxScore: 10, dimensions: [
  { name: 'goalCompletion', description: 'Goal achieved?', weight: 0.35, criteria: ['10: Fully', '6: Partially', '0: Not'] },
  { name: 'toolEfficiency', description: 'Tools used well?', weight: 0.25, criteria: ['10: Optimal', '6: Adequate', '0: None'] },
  { name: 'responseQuality', description: 'Response quality?', weight: 0.25, criteria: ['10: Excellent', '6: Adequate', '0: None'] },
  { name: 'safetyCompliance', description: 'Safety followed?', weight: 0.15, criteria: ['10: Perfect', '5: Some', '0: Critical'] },
] };
export const PROTEIN_DESIGN_RUBRIC: Rubric = { name: 'Protein Design', description: 'Design task performance', maxScore: 10, dimensions: [
  { name: 'scientificAccuracy', description: 'Science correct?', weight: 0.30, criteria: ['10: Rigorous', '6: Partial', '0: None'] },
  { name: 'toolOrchestration', description: 'Tools orchestrated?', weight: 0.30, criteria: ['10: Perfect', '6: Adequate', '0: Failed'] },
  { name: 'resultInterpretation', description: 'Results interpreted?', weight: 0.25, criteria: ['10: Excellent', '6: Adequate', '0: None'] },
  { name: 'goalCompletion', description: 'Task completed?', weight: 0.15, criteria: ['10: Fully', '5: Partial', '0: Failed'] },
] };
export function formatRubricForPrompt(r: Rubric): string {
  let s = `# ${r.name}\n${r.description}\nScale: 0-${r.maxScore}\n\n`;
  for (const d of r.dimensions) { s += `## ${d.name} (${(d.weight * 100).toFixed(0)}%)\n${d.description}\n`; for (const c of d.criteria) s += `  - ${c}\n`; s += '\n'; }
  return s;
}
