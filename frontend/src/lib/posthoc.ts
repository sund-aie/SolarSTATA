/* Selectors over the analyze-results history.
 *
 * Used by VisualizeStep so the bar form can offer significance
 * brackets when the user has already run a matching oneway with
 * a posthoc correction. The selector reads the existing oneway
 * output and returns it verbatim — no new statistics computed.
 */

import type { AnalyzeRecord, OnewayResponse } from "./types";

export type OnewayPosthocBlock = NonNullable<OnewayResponse["result"]["posthoc_block"]>;

/** Return the most recent oneway posthoc block in `records` that
 *  matches the given depvar + groupvar. Returns null when:
 *    - no oneway record exists,
 *    - the most-recent matching oneway was run with posthoc="none",
 *    - or none of the records reference this (depvar, groupvar) pair.
 *
 *  Pure function. Caller is responsible for passing the live
 *  analyzeRecords slice from the store.
 */
export function lastOnewayPosthoc(
  records: AnalyzeRecord[],
  depvar: string,
  groupvar: string,
): OnewayPosthocBlock | null {
  for (let i = records.length - 1; i >= 0; i--) {
    const r = records[i];
    if (r.kind !== "oneway") continue;
    const result = (r.payload as OnewayResponse | undefined)?.result;
    if (!result || !result.posthoc_block) continue;
    if (result.depvar !== depvar || result.groupvar !== groupvar) continue;
    return result.posthoc_block;
  }
  return null;
}
