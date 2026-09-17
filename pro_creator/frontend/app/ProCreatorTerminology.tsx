"use client";

import { useEffect } from "react";

const BRAND_REPLACEMENTS: ReadonlyArray<readonly [RegExp, string]> = [
  [/X'treamers/g, "ProCreators"],
  [/X’treamers/g, "ProCreators"],
  [/X'treamer/g, "ProCreator"],
  [/X’treamer/g, "ProCreator"],
];

function applyBrandTerminology(root: Node) {
  if (typeof document === "undefined") return;

  const replaceNode = (node: Text) => {
    const current = node.nodeValue ?? "";
    let next = current;
    for (const [pattern, replacement] of BRAND_REPLACEMENTS) {
      next = next.replace(pattern, replacement);
    }
    if (next !== current) node.nodeValue = next;
  };

  if (root.nodeType === Node.TEXT_NODE) {
    replaceNode(root as Text);
    return;
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current) {
    replaceNode(current as Text);
    current = walker.nextNode();
  }
}

/**
 * Temporary compatibility bridge while legacy community copy still exists in the
 * large workflow module. It changes rendered user-facing terminology only and
 * leaves routes, IDs, API contracts, and persisted data untouched.
 */
export default function ProCreatorTerminology() {
  useEffect(() => {
    applyBrandTerminology(document.body);

    const observer = new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          applyBrandTerminology(node);
        }
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return null;
}
