export const documentPages = [
  ["guide", "doc.guide"],
  ["integration", "doc.integration"],
  ["packages", "doc.buildArtifacts"],
  ["licenses", "doc.licensesAndRedistribution"],
  ["self-build", "doc.buildFromSource"],
  ["reference", "doc.reference"],
  ["history", "doc.updateHistory"],
] as const;
export type DocumentPage = (typeof documentPages)[number][0];
export function isDocumentPage(value: string): value is DocumentPage {
  return documentPages.some(([page]) => page === value);
}
