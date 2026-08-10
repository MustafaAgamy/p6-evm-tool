// Shared mutable state — import { state } and mutate state.xxx = value
export const state = {
  serverPort:        null,
  currentResult:     null,
  currentXmlPath:    null,
  currentCachedPath: null,
  currentSnapshotId: null,
  currentModules:    null,   // {modules, module_order}
  currentModule:     null,   // selected module key ('dangling' | 'float')
  baselinePath:      null,   // cached path of an attached baseline (XER updates); drives PDF re-gen
  baselineName:      null,   // filename of the attached baseline, for the banner
  baselineMatched:   null,   // activities matched between update and baseline (by Id)
  baselineTotal:     null,   // total update activities, for the matched/total count
  aiReport:          null,   // dormant — AI review (future Pro edition)
  aiReferencePath:   null,   // dormant
  aiReferenceName:   null,   // dormant
  constructReport:   null,   // Constructability Review report dict (rule + KB)
  constructForcedType: null, // user-overridden project sub-type, if any
};
